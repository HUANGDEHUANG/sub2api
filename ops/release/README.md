# 唯一发布链路

1. 从 `production` 创建功能分支；不得修改历史快照。
2. 改动后执行定制守卫及与变更相关的测试。清单中的源码锚点是保留检查，不替代行为测试。
3. 审核后合回 `production`，创建不可移动的 `rel/buaga-*` 标签。
4. 在干净工作区执行 `python3 ops/release/package.py <tag> <绝对输出路径.tar.gz>`。
5. 上传包和独立 JSON 清单。服务器运行已安装的 `verify_package.py`，校验 SHA256、Git commit、定制功能，再解包。
6. 主站构建使用 `build-bluegreen.sh`；镜像必须继承当前定制运行时，前端从同一 Git 包重新构建。
7. 按现有流程隔离测试、验证定制界面和健康检查，再平滑切换。打包或构建不等于上线。

主站切换验收必须包含价格监控容器内的健康检查与管理 API 只读认证检查。
不能只看主站 HTTP 200：Docker 网络别名可能在重建后丢失。
监控的 `SUB2API_API_BASE_URL` 及 `.env` 必须指向实际承接流量的当前容器；
采用容器名绑定时，每次切换须同步更新监控，不能遗留在已退役实例上。

部署后必须更新 `/home/serveradmin/releases/buaga-current.json` 的实际镜像、源码 commit、tag 和源码包校验和。
生产主站与价格监控是独立服务：不能用监控发布标签冒充主站部署记录。

历史 `release.py` / `verify-backend.sh` 仅保留为原发布证据，不得再作为候选创建/构建入口。
服务器 `prepare-custom-upgrade.py --check` 继续校验线上镜像；旧的目录复制方式已禁用。
服务器未安装 Git，权威 Git 操作都在 Mac 完成。

迁移基线保留 R3 原始源码包与其 SHA256，另记录 Git 导出包；二者压缩格式不同，校验和不会相同，但每个源码文件内容一致。
旧目录只读化保留已有未提交修改、测试依赖和数据，不删除文件。
