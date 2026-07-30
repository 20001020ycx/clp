# Spider-orchestrated compression on Kubernetes — stock-image E2E guide

Reproduces the full product loop of [y-scope/clp#2418](https://github.com/y-scope/clp/pull/2418)
using **only CI-published images** — no local builds: logs seeded in S3 (in-cluster MinIO stand-in)
→ log-ingestor scan → compression job → compression coordinator → Spider → archives in S3 +
metadata in CLP's DB → search via the api-server returns the original events.

Verified end-to-end on 2026-07-30 (images built by CI from `main` commit `5a662974`).

## Prerequisites

- Docker, [kind](https://kind.sigs.k8s.io/), Helm ≥ 3.14, kubectl.
- ~2 GB of image pulls; no AWS account needed.

> [!NOTE]
> Until CLP's artifact workflow finishes stitching the multi-arch manifest for the latest `main`,
> the `clp-package:main` tag may lag behind `clp-package:main-amd64`. This guide pins `main-amd64`
> explicitly; once `:main` is current you can drop that `--set` and the pull-policy overrides.

## 1. Get the chart (PR branch)

```bash
git clone -b feat/2026-07-21-spider-storage-subchart https://github.com/20001020ycx/clp.git clp-spider-e2e
cd clp-spider-e2e/tools/deployment/package-helm
helm dependency update .   # Expected: "Downloading spider from repo https://github.com/y-scope/spider/raw/gh-pages"
```

## 2. Cluster + images

```bash
kind create cluster --name clp-test
docker pull ghcr.io/y-scope/clp/clp-package:main-amd64
docker pull ghcr.io/y-scope/clp/clp-spider-worker:main
kind load docker-image ghcr.io/y-scope/clp/clp-package:main-amd64 ghcr.io/y-scope/clp/clp-spider-worker:main --name clp-test
```

## 3. In-cluster S3 (MinIO) + input logs

Save as `minio-demo.yaml`:

```yaml
# Demo-only in-cluster S3 (MinIO) so the log-ingestor flow runs without an AWS account.
apiVersion: "apps/v1"
kind: "Deployment"
metadata:
  name: "minio"
  labels:
    app: "minio"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: "minio"
  template:
    metadata:
      labels:
        app: "minio"
    spec:
      containers:
        - name: "minio"
          image: "minio/minio:RELEASE.2025-04-22T22-12-26Z"
          args: ["server", "/data", "--console-address", ":9001"]
          env:
            - name: "MINIO_ROOT_USER"
              value: "minio-demo-key"
            - name: "MINIO_ROOT_PASSWORD"
              value: "minio-demo-secret-123"
          ports:
            - name: "s3"
              containerPort: 9000
            - name: "console"
              containerPort: 9001
          readinessProbe:
            httpGet:
              path: "/minio/health/ready"
              port: "s3"
            initialDelaySeconds: 3
            periodSeconds: 2
---
apiVersion: "v1"
kind: "Service"
metadata:
  name: "minio"
  labels:
    app: "minio"
spec:
  selector:
    app: "minio"
  ports:
    - name: "s3"
      port: 9000
      targetPort: "s3"
    - name: "console"
      port: 9001
      targetPort: "console"
```

Deploy it, then seed 4 JSON log files:

```bash
kubectl apply -f minio-demo.yaml
kubectl wait --for=condition=ready pod -l app=minio --timeout=120s
kubectl run minio-seed --rm -i --restart=Never --image=minio/mc --command -- sh -c '
  mc alias set local http://minio:9000 minio-demo-key minio-demo-secret-123 &&
  mc mb -p local/clp-logs local/clp-archives &&
  for i in 1 2 3 4; do
    printf "{\"ts\":%d,\"level\":\"INFO\",\"msg\":\"demo log line %d\"}\n" $((1700000000+i)) $i > /tmp/app-$i.jsonl
    mc cp /tmp/app-$i.jsonl local/clp-logs/demo-logs/app-$i.jsonl
  done && mc ls local/clp-logs/demo-logs/'
```

Expected: the seed pod lists `app-1.jsonl` … `app-4.jsonl` (57 B each).

## 4. Install CLP with Spider enabled

Save as `stock-values.yaml`. This is ALL the configuration Spider mode needs — the chart's default
values carry the entire worker wiring (image, env, config/secret mounts, staging volume):

```yaml
spider:
  enabled: true
  spiderConfig:
    worker:
      # One worker keeps the verification steps deterministic (the chart default is 4).
      replicas: 1

clpConfig:
  # Spider mode requires S3 for both log input and archive output (the coordinator refuses to
  # start otherwise). MinIO stands in for S3 here.
  logs_input:
    type: "s3"
    aws_authentication:
      type: "credentials"
      credentials:
        access_key_id: "minio-demo-key"
        secret_access_key: "minio-demo-secret-123"

  archive_output:
    storage:
      type: "s3"
      s3_config:
        endpoint_url: "http://minio:9000"
        # No region_code: with a custom endpoint, the query path builds the archive URL as
        # http://<region>.<endpoint-host>/..., which doesn't resolve in-cluster.
        bucket: "clp-archives"
        key_prefix: "archives/"
        aws_authentication:
          type: "credentials"
          credentials:
            access_key_id: "minio-demo-key"
            secret_access_key: "minio-demo-secret-123"
```

Install (from `tools/deployment/package-helm`):

```bash
helm install test . -f stock-values.yaml \
  --set image.clpPackage.tag=main-amd64 \
  --set image.clpPackage.pullPolicy=IfNotPresent \
  --set spider.image.worker.pullPolicy=IfNotPresent
```

Wait ~5 min. The Spider pods crash-loop until Spider's DB comes up — a few restarts are normal.
Expected (note: no Celery `compression-scheduler`/`compression-worker` pods; Spider resources are
prefixed with the release name):

```bash
kubectl get pods | grep -E "spider|compression|ingestor"
```

```
test-clp-compression-coordinator-...   1/1  Running
test-clp-log-ingestor-...              1/1  Running
test-spider-database-0                 1/1  Running
test-spider-scheduler-...              1/1  Running
test-spider-storage-...                1/1  Running
test-spider-worker-...                 1/1  Running
```

The coordinator registered itself in CLP's DB:

```bash
DBPASS=$(kubectl get secret test-clp-database -o jsonpath='{.data.password}' | base64 -d)
kubectl exec test-clp-database-0 -- mariadb --table -u clp-user -p$DBPASS clp-db \
  -e "SELECT rg_name, rg_id FROM spider_resource_groups;"
# -> compression-coordinator | 1
```

## 5. Ingest → compress through Spider

Start ingestion — `{"id":1}` is the success response. Do NOT add a `"region"` field when using a
custom `endpoint_url`:

```bash
kubectl run curl-ingest --rm -i --restart=Never --image=curlimages/curl:8.14.1 -- \
  -sS -X POST http://test-clp-log-ingestor:3002/s3_scanner \
  -H 'Content-Type: application/json' \
  -d '{"bucket_name": "clp-logs", "key_prefix": "demo-logs/", "endpoint_url": "http://minio:9000",
       "scanning_interval_sec": 5, "buffer_config": {"timeout_sec": 10}}'
```

~30–60 s later, all 4 objects are `compressed`, the job `SUCCEEDED` (`status=2`) through Spider
(`spider_id=1`, `duration` populated), and the archive is registered:

```bash
kubectl exec test-clp-database-0 -- mariadb --table -u clp-user -p$DBPASS clp-db \
  -e "SELECT id, \`key\`, status, compression_job_id FROM ingested_s3_object_metadata;
      SELECT id, status, num_tasks, spider_id, duration FROM compression_jobs;
      SELECT id, uncompressed_size, size FROM clp_default_archives;"
```

The same archive ID appears as an object in MinIO:

```bash
kubectl run minio-ls --rm -i --restart=Never --image=minio/mc --command -- sh -c \
  'mc alias set local http://minio:9000 minio-demo-key minio-demo-secret-123 >/dev/null && mc ls -r local/clp-archives/'
# -> archives/default/<archive-id>
```

## 6. Search the compressed result

```bash
kubectl run curl-query --rm -i --restart=Never --image=curlimages/curl:8.14.1 -- \
  -sS -X POST http://test-clp-api-server:3001/query \
  -H 'Content-Type: application/json' \
  -d '{"query_string": "msg: \"demo log line*\"", "datasets": ["default"], "ignore_case": true,
       "max_num_results": 10, "buffer_results_in_mongodb": true}'
# -> {"query_results_uri":"query_results/1"}

sleep 15
kubectl run curl-results --rm -i --restart=Never --image=curlimages/curl:8.14.1 -- \
  -sS http://test-clp-api-server:3001/query_results/1
```

Expected — the original four events, served from the Spider-compressed archive:

```
data: {"ts":1700000001,"level":"INFO","msg":"demo log line 1"}
data: {"ts":1700000002,"level":"INFO","msg":"demo log line 2"}
data: {"ts":1700000003,"level":"INFO","msg":"demo log line 3"}
data: {"ts":1700000004,"level":"INFO","msg":"demo log line 4"}
```

## 7. Teardown

```bash
helm uninstall test
kubectl delete -f minio-demo.yaml
kubectl delete pvc --all
# or simply:
kind delete cluster --name clp-test
```

## Notes

- The `kubectl run curl-…` wrappers exist because the Services are ClusterIP — a bare `curl` from
  the host cannot resolve `test-clp-log-ingestor`.
- Worker logs are error-only by default (no `RUST_LOG`). The DB rows, the MinIO object, and the
  search results above are the verification evidence. To watch Spider's execution manager and the
  task library's tracing, set `RUST_LOG=info` via `spider.spiderConfig.worker.extra_envs` — note
  that overriding `extra_envs` replaces the chart-default list, so restate the three default
  entries alongside it (see the chart's `values.yaml`).
- The credentials in this guide are fixed public demo defaults from the charts — do not reuse
  them outside a demo.
