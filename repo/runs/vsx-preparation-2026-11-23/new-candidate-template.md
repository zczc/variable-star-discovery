# 新候选的 VSX 材料模板

本地模板，2026-11-23。参照四条公开获批记录和当日官方指南编写。所有方括号都是待填项，不能原样提交；未解决来源或查重问题时保持 `submission_ready=false`。

## 1. 表单准备

| 项目 | 填写内容 | 必须保留的依据 |
|---|---|---|
| 主名称／其他名称 | [TIC／Gaia／2MASS 等准确编号] | 交叉匹配结果，Gaia 编号用字符串 |
| 坐标 | [RA, Dec；坐标系、历元、来源] | 自行传播方法、误差和查找图 |
| 变星类型 | [证据支持的类型及不确定性] | 波形、颜色／光谱、周期特征；未知时不硬填物理类型 |
| 周期 | [P ± 误差，单位天] | 多时段结果、半倍／两倍竞争、误差估计方法 |
| 历元 | [事件定义、时刻、时间标准和误差] | 原始时间头和转换；BJD_TDB 不能直接改名 HJD |
| 星等及变幅 | [同波段最大／最小，或有来源的目录星等＋另一波段幅度] | 波段、标定、混光和幅度定义分别说明 |
| 发现者／提交者 | [真实姓名及各自贡献] | 先前候选、论文和巡天贡献；两种身份不能混用 |
| 引用 | [论文 bibcode；无 bibcode 时按指南提供链接] | 实际读到的支持内容和数据版本 |
| 备注 | [英文正文，见下] | 来源疑点、复合变化、次周期及处理说明 |

## 2. 英文备注结构

> [OBJECT] shows [DESCRIBE THE OBSERVED VARIATION] in [SURVEY / PRODUCT / SECTORS / DATE RANGE]. We measure a photometric period of [P] d with [UNCERTAINTY AND METHOD], adopting [EVENT DEFINITION] at [EPOCH AND TIME STANDARD]. The signal is present in [INDEPENDENT EPOCHS]; [LIST FAILURES, CONFLICTING PERIODS OR LIMITATIONS].
>
> [STATE HOW SOURCE LOCALIZATION WAS TESTED AND WHAT NEIGHBORS REMAIN UNRESOLVED]. The measured amplitude is [VALUE, PASSBAND, FULL/SEMI-AMPLITUDE, FLARE MASK AND DILUTION TREATMENT]. The quoted catalog magnitude [VALUE, BAND, SOURCE] is separate from this amplitude.
>
> Searches of [CATALOGS AND PRIMARY LITERATURE, WITH DATE AND IDENTIFIERS] found [ACTUAL RESULTS]. [DISCLOSE PREVIOUS CANDIDATE / VARIABLE REPORTS AND FAILED SEARCHES]. [STATE ACTUAL CONTRIBUTIONS AND PRIOR CREDIT].

存在前人报告时，删除任何首次发现措辞，按文献补录或修订处理。查无匹配只能描述搜索范围内的结果，不能写成“保证无人发现”。

## 3. 附件包

1. `01-lightcurve.png`：按时间的光变，注明波段、数据产品、时间单位和筛点条件；耀发与周期变化可分图，但保留原图。
2. `02-phase.png`：采用周期与历元的相位图；区分不同观测时段。食双星另看两次极小，排除半周期。
3. `03-period-comparison.png`：必要的候选周期比较及跨时段支持，不只展示最好的一段。
4. `04-finder-chart.png`：北、东、比例尺、目标和近邻编号；附来源定位及污染检查说明。
5. `references.md` 和 `analysis-notes.md`：数据地址、论文、方法、版本和不确定性。内部分析档案不等同于官方附件格式。

范例图只用于学习写法，不能作为我们目标的证据。合并不同波段时，图中写明平移量，不能将显示平移当真实测光标定。

## 4. 从草稿到提交

按 [VSX 官方指南](https://vsx.aavso.org/index.php?view=about.notice)再核对当日要求。在登录后的 New Star Form 用 Check name 和 Spot check 排除重复；已存在的对象走修订，前人已报道而尚未录入的对象按文献补录。先保存 Draft only，核对字段与附件，再作正式提交。

这是操作路线，不表示本项目已登录、保存线上草稿或提交。正式提交前，先给用户查看确定的对象、真实署名、最终字段和附件。当前模板中没有可提交对象。
