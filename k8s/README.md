# sm-event-bus Kubernetes 部署

企业级部署清单，与 SECURITY_BASELINE.md / DEPLOYMENT_CHECKLIST.md 对齐。

## 前提

1. 命名空间 `sm` 已创建：`kubectl create namespace sm`
2. 密钥 `sm-secrets` 已创建（字段：`internal_api_key`、`sm4_key_hex`）：
   ```bash
   kubectl -n sm create secret generic sm-secrets \
     --from-literal=internal_api_key=<值> \
     --from-literal=sm4_key_hex=<32位十六进制>
   ```
3. 数据卷 PVC `sm-event-bus-data`（按存储环境预创建，或改用 emptyDir）。

## 部署

```bash
kubectl apply -f k8s/
```

## 资源

- `deployment.yaml`：Deployment（2 副本；非 root(10001)、只读根文件系统、seccomp RuntimeDefault、capabilities drop ALL、存活/就绪探针、资源限额；环境变量经 `sm-secrets` 注入）。
- `service.yaml`：ClusterIP 服务（端口 8410）。
- `networkpolicy.yaml`：默认拒绝（Deny-all），仅允许同命名空间 SM 服务与 API 网关访问，出站仅限审计中心(8320)/通知中心(8470)/DNS(53)。

## 说明

- 镜像 `ghcr.io/luoshitianchen/sm-event-bus:latest` 按实际发布仓库与 tag 替换。
- 生产建议副本数 ≥2 并配置 HPA；数据库使用外部高可用存储（本清单以 PVC 挂载 SQLite 文件为基线）。
