# VSX 范例与材料草稿

2026-11-23。已核对四份获批的公开 VSX 记录，并参照其字段、备注和图表编写材料。查重同时发现，TIC 302959739 已在 Feinstein 等人 2024 年研究的最终耀发表中出现，因此退出本项目的首次变星发现候选。原 16 个候选累计排除 15 个，剩余 HD 43737A/B 来源未解。当前确认的新发现、可提交对象和正式提交数均为 0。

交付文件：

- [四份公开范例及图表](../repo/runs/vsx-preparation-2026-11-23/index.html)
- [TIC 302959739 英文复核／文献补录草稿](../repo/runs/vsx-preparation-2026-11-23/tic-302959739-draft.md)
- [新候选的可复用提交模板](../repo/runs/vsx-preparation-2026-11-23/new-candidate-template.md)
- [当前候选状态](../repo/runs/vsx-preparation-2026-11-23/candidate-status-update.json)、[查重证据](../repo/runs/vsx-preparation-2026-11-23/prior-work.json)、[37 条原表耀发记录](../repo/runs/vsx-preparation-2026-11-23/published-flare-rows.csv)

## 公开范例教会我们什么

检查范围是公开字段、备注、参考文献、附件及获批修订记录。没有取得私下申请原文或完整审核对话，不能称为四份完整申请档案。四页均核对到当前修订的 approved 图标；本轮实际查看五张原作者附件图，其他附件仅按页面记录描述。

| 公开记录 | 核对到的字段 | 可参考的写法 |
|---|---|---|
| [GSC 04448-01982](https://vsx.aavso.org/index.php?view=detail.top&oid=625294) | EW；P＝0.520446 天；HJD 2458417.74；13.29–13.51 V；2018-11-24 获批修订记录 | 相位图、周期、历元、波段和数据源完整；备注另写次极小 13.47 V |
| [TIC 188835620](https://vsx.aavso.org/index.php?view=detail.top&oid=10876488) | EA+ROT；主周期 22.2167 天；10.34 V (0.12)TESS；2026-11-04 获批修订记录 | V 目录星等与 TESS 变幅分开；备注另列 16.91 天自转及其历元、变幅，发现者包含前人和后续团队 |
| [ASASSN-26fs](https://vsx.aavso.org/index.php?view=detail.top&oid=10876491) | BY+UV；P＝0.588651 天；HJD 2459047.96；12.5–15.83 g；2026-11-05 获批修订记录 | BY 变幅 0.20 g 单列；周期图与包含耀发的时间光变图分开。提交者 Otero 与发现者 ASAS-SN 不同 |
| [Barlad V105](https://vsx.aavso.org/index.php?view=detail.top&oid=10876522) | EA；P＝1.884565 天；HJD 2458766.175；12.15 V (0.072)TESS；2026-11-21 获批修订记录 | 联合 TESS 与地面数据，另附主、次食局部图；本轮查看主图，未查看两个局部附件 |

不同波段数据为绘图作平移时，图中应注明；平移后的点不能当成同一真实波段的测光。目录星等也不能与另一波段的变幅相加减，伪造最大／最小星等。附件上传时间可能包含草稿阶段，不能据此计算审核耗时。

这些范例说明材料如何表达，不意味着本项目也可以填写同样的类型。TIC 302959739 的类型、历元和本征变幅仍为空；不能因为相似对象是 BY+UV，就照抄其分类。

## 为什么撤下 TIC 302959739

[Feinstein et al. (2024)](https://doi.org/10.3847/1538-3881/ad4edf) 的 [全文](https://arxiv.org/html/2405.00850)明确链接作者数据仓库。已核对该仓库的 `paper` 分支，并固定到 [9113bbb9de9114ea4ee74b73ddbc6cd9bbcb3411](https://github.com/afeinstein20/young-stellar-flares/tree/9113bbb9de9114ea4ee74b73ddbc6cd9bbcb3411)。`main` 分支没有这些数据，不能据此误判未收录。

| 作者公开文件 | 本轮精确匹配 |
|---|---|
| `TIC_catalog_v6.csv`，6,824 行 | TIC 302959739；2MASS J09042304-7137155；RA 136.096059766959°、Dec −71.620960633465°；身份与本项目一致 |
| `combined_prot_flarerate_v6.csv`，3,986 行 | Prot＝0.437769157672309 天；e_Prot＝0.00427381457161783 天；**Good＝0** |
| `final_flare_catalog_v6.csv`，26,355 行 | **37 条耀发记录精确指向该 TIC** |
| `src/scripts/prot_histograms.py`，第 22 行 | `tab = tab[tab['Good'] == 1]`，目标未进入该筛选子集 |

作者候选周期与我们的约 0.4377 天接近，但 Good＝0 的数值不能写成可靠周期确认。`e_Prot` 只是作者表值，不是我们的误差估计。该 CSV 的 Good＝1 行数为 1,848，而正文说可靠周期共 1,847 个；这个总体差异尚未解释，本轮没有用它计算任何成功率。对本星的判断依赖准确 TIC、Good＝0 和最终耀发表中的 37 条记录。

最终耀发表已构成明确的先前变光报告。即使以后证实我们的周期更准确，也只能再讨论周期复核等具体贡献，不能重新称为首次发现这颗变星。作者仓库快照的提交日期是 2024-05-01；周期表最近变更的提交日期为 2023-12-19。这些是 Git 元数据，不当成独立认证的首次公开时间；2024 年论文及其数据链接已经足以排除本项目的首次发现主张。

第 36 区强突增附近有作者表中的峰时线索，但本轮未完成作者 `tpeak` 时间标准的核验，也未作正式事件配对。不能把作者的模型峰时、能量或概率写成我们的独立测量。

## 草稿做到哪一步

英文稿已写明前人发现、我们的七段观测结果、失败与分歧、近邻风险，以及未测出的量。另有字段清单、附件审计和参考文献。它是一份可审查的本地复核稿，尚不能提交。

| 项目 | 当前状态 | 缺什么 |
|---|---|---|
| 首次发现资格 | 不成立 | 补更多图不能恢复；该目标转出首次发现队列 |
| 变化证据 | 既有耀发报告；本项目六段出现约 0.4377 天变化 | 不能把跨产品／跨时段分歧隐去 |
| 信号来源 | PRF 诊断偏向目标附近 | 真实天空定位误差尚未标定，5.09 角秒近邻未被充分排除 |
| 最终周期和类型 | 原合并结果 unresolved | 物理周期、倍周期歧义、类型及误差仍待确定 |
| 星等和历元 | 仅有可追溯的目录 Tmag；无采用历元 | 需测量和标定，不能把 BTJD 加常数改称 HJD |
| 目录补录 | 可作为另一路径考虑 | 先刷新 VSX 身份查询，确定是否确有补录空间；补齐科学字段与附件并正确归属 |
| 下一颗 HD 43737A/B | 原候选保留，未新增检测 | 6.17 角秒、近等亮双星的变光分量未定；新颖性也未确认 |

SkyMapper DR4 已返回目标与近邻各自的目录身份，Gaia 编号一致。目标有 37 条逐次测光，近邻 11 条；这与论文的 37 个耀发事件是不同数据。多条同场 g/r 测光带混合标记，部分 PSF 残差很大；近邻主表 `flags_psf=12`，目标为 0。目标最亮的若干离群点同时误差和残差很大，不能视为独立耀发证据。本轮没有下载 SkyMapper 图像或拟合其周期，未据此排除近邻。FWHM 单位按官方元数据为像素。

## 真正提报时怎么做

依据当日 [VSX 官方指南](https://vsx.aavso.org/index.php?view=about.notice)：公开巡天分析可提交；周期变星需提供可核实的周期、历元、类型、测光与图表。第 IV.c 节允许适用情况下分列目录星等与另一波段变幅；第 V.d 节提醒 TESS 过度校正；第 VI 节允许补录已有文献，第 VI.c 节要求有 bibcode 时使用 bibcode。

材料齐全后，用实际用户账号进入 New Star Form，先做 Check name／Spot check，已有条目走修订；保存 Draft only 后核对全部字段、参考文献和附件，再正式提交。模板已经按这个顺序整理。本轮没有登录、保存线上草稿、发送邮件或正式提交，也没有替用户填写发现者姓名。

## 保存与复核

`sources/` 保留访问日期、请求、响应及失败。Google／DuckDuckGo 返回受限页面的尝试没有形成有效搜索；VizieR 的 catalog not found、超时及 GitHub 匿名 API 限流均不计为无匹配。GitHub 后续使用已有授权的只读 API 取得所需元数据，未保存令牌。这是单人定向查重，不是穷尽的系统综述。

离线重建只读取保存的回执，不联网、不重新检测或改门槛：

```bash
repo/.venv/bin/python repo/benchmarks/report_vsx_preparation.py
repo/.venv/bin/python repo/benchmarks/report_vsx_preparation.py --verify-only
repo/.venv/bin/python repo/benchmarks/report_labelled_baseline.py --verify-only
```

目标行按 TIC 精确匹配，科学计数法及带 `.0` 的 TIC 使用十进制解析；Gaia 编号保留字符串。原 11 月 20 日和 22 日的结果保留，新状态另写 `candidate-status-update.json`。本轮没有修改检测科学代码、旧预测或首次基线。检查结果见运行目录的 `verification.json`；全部新材料及源回执列于 `manifest.json`。

## 文献与方法来源

- Feinstein, A. D., et al. (2024). *Evolution of Flare Activity in GKM Stars Younger Than 300 Myr over Five Years of TESS Observations*. AJ, 168, 60. [doi:10.3847/1538-3881/ad4edf](https://doi.org/10.3847/1538-3881/ad4edf)。论文与作者表共同支持先前报告结论，Crossref 用于核对出版元信息。
- [SkyMapper DR4 数据说明](https://skymapper.anu.edu.au/data-release/dr4/)。原查询、表结构和质量标记说明已保存。
- [VSX 提交指南](https://vsx.aavso.org/index.php?view=about.notice)及上列四条公开记录。图表归原作者所有，示例副本仅用于注明出处的学习与核验，不作为本项目目标证据。
- 使用 `literature-review` 技能组织查重与来源审计；按其说明，在方法来源列入 Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026), *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*, [arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065)。已核对当前 arXiv 记录。这项软件／方法引用不支持恒星的科学判定。
