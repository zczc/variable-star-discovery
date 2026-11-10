# 2026-11-09 前期试验

本目录保存 33 个目标的探索性分析。29 个完成光变初筛，4 个被近位置 VSX 匹配预筛掉；3 个做了多观测区比较，2 个做了像素信号定位。目前没有完成全部验证的新发现。

科学结论、查重线索和未完成事项见 [前期试验记录](../../../doc/05-pilot-2026-11-09.md)。

## 文件说明

| 文件 | 用途 |
|---|---|
| `scan.py` | VSX 位置预筛、光变下载、周期初筛及分段比较 |
| `followup.py` | 为三个固定目标查询并分析其他观测区 |
| `localize.py` | 为两个固定目标画像素相干信号图，并输出多观测区光变图 |
| `mast-s85.json` | 本次初始观测产品清单，不是整个 Sector 85 的完整目标列表 |
| `scan-results.json`、`scan-*.json` | 初筛输出及 VSX 邻域结果 |
| `observations-*.json`、`followup-*.json` | 追加观测产品与分析结果 |
| `tic-neighbors-*.json`、`products-*.json` | 邻近目标和产品查询结果 |
| `localization.json`、`pixels-*.npz` | 像素定位结果及用于图表的数组 |
| `*.png`、`lightcurve-display.json` | 历史图表和展示数据；以项目文档中的当前结论为准 |
| `*.fits` | 38 个原始观测或诊断文件，按用户要求随公开仓库保存 |
| `migration-manifest.json` | 已迁移文件的来源、字节数、SHA-256 和路径调整说明 |
| `requirements.txt`、`environment.json` | 前期运行和迁移检查所用的主要依赖版本与 Python 环境 |
| `migration-verification.json` | 迁移后的数据完整性和离线重算检查结果 |

## 本次迁移做了什么

96 个历史文件从临时目录复制到这里，原目录保留不动。FITS、图片和数组按字节保留；JSON 中的本地 `file` 字段改为文件名，其余数值不变。

`scan.py` 的工作目录取脚本所在绝对路径，读光变时可以使用本目录下的文件名；`scan.py` 和 `followup.py` 新输出的 `file` 字段也改为文件名。没有修改周期算法或筛选参数。原文件和迁移文件的校验值都在清单中。

未复制原虚拟环境、缓存、第三方论文全文或临时网页。TESS-L8 网站的历史查重线索记录在项目文档中，未保存完整网页证据。

## 准备 Python 环境

历史试验使用 Python 3.12.6。`requirements.txt` 记录相关库的实测版本，不是包含全部间接依赖的锁文件，也未在一台干净机器上重新安装验证。

在 `repo/` 目录中可以按以下步骤准备环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r experiments/2026-11-09-pilot/requirements.txt
```

## 先离线读取一个已有结果

以下命令从 `repo/` 运行，只使用已保存的 FITS，不查询目录、不下载数据，也不覆盖原结果。

```bash
.venv/bin/python -B - <<'PY'
import json
import sys
from pathlib import Path

root = Path('experiments/2026-11-09-pilot').resolve()
sys.path.insert(0, str(root))
from scan import analyze

saved = json.loads((root / 'scan-458747716.json').read_text())
result = analyze(root / saved['file'])
print('重新计算的周期（天）：', result['period_d'])
print('历史初筛周期（天）：', saved['period_d'])
PY
```

预期周期约 2.2783806253 天。复现这个值只证明路径和原分析计算一致，不表示该对象通过了发现审核。

## 重新运行整个试验

以下脚本会进行网络请求或覆盖部分结果，应先理解其行为并保留历史输出。

```bash
.venv/bin/python experiments/2026-11-09-pilot/scan.py
.venv/bin/python experiments/2026-11-09-pilot/followup.py
.venv/bin/python experiments/2026-11-09-pilot/localize.py
```

`followup.py` 和 `localize.py` 在导入时也会执行工作，不要把它们当作没有副作用的通用模块。`localize.py` 需要两个已保存的像素文件，当前脚本不负责下载它们。

从公开 GitHub 仓库克隆时会带有这 38 个 FITS。需要单独恢复文件时，也可以按 `migration-manifest.json` 的 `mast_uri`，向清单记录的下载接口传递 `uri` 参数重新下载，再用 SHA-256 检查。下载恢复尚未封装成独立脚本。

## 已知局限

- 输入样本和追加目标是固定的，没有完整的采样设计、目录分页和恢复机制。
- 初筛只覆盖约 0.05–8 天的周期，10 分钟分箱可能损失短时信号。
- 10 角秒内匹配 VSX 只是位置筛查；无匹配不等于新发现。
- 周期图最高峰及前后半段比较不能替代完整的周期误差、噪声和混叠评估。
- 像素定位是探索性分析，信噪比假设简化，尚未完成精细的来源拟合。
- 查重尚未完成，外部查询失败不能当作“没有文献”。

后续应保留这一轮试验，另建运行目录和参数化流程，避免新分析覆盖旧证据。
