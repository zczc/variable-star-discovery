# 标签来源核对

检索日期：2026-11-12。按 literature-review 技能核对原始论文；这是针对标签数据集的单人定向检索，不是系统综述。

## 采用：Skarka et al. 2022

论文 DOI：https://doi.org/10.1051/0004-6361/202244037 。arXiv:2207.12922v2。

摘要写道：

> We find clear signs of variability in 3025 of 5923 studied stars (51 %).

第 3 节说明逐颗检查各类产品，并优先使用 SPOC 短采样资料：

> We performed careful individual investigation of all available datasets for each star giving the preference to the SPOC SC data (where available) that seem to be the most reliable. The identification of variability and subsequent classification was performed on an individual basis.

第 4 节说明：

> For the stars that are certainly variable but we were not able to determine the variability type, we used 'VAR'.

本次不纳入 VAR 或含歧义的类型，避免它们与文中讨论的仪器疑点混在一起。论文说明 Table 5 包含全研究样本；VizieR 完整导出有 5,923 行，其中空白 VType 恰有 2,898 行，同时 f、dT 为空，与全文 5,923 − 3,025 一致。负例是这份已逐颗检查的完整样本中的作者非变光类别，不是因一般目录查不到而推定。表内十个空白 VType 但有 VSX 记录的对象排除，重复 TIC 的两行也排除。

标签的测量范围：TESS Cycle 2，Sector 14–26；长短采样、SPOC 与 QLP 比较；没有统一变幅阈值。当前测试只采用同一 Cycle 的两个 SPOC 2 分钟时段。少量图像和产品修正可能不同于作者当年的下载版本，因此后续发现与标签不符时保留分歧，不修改初次评分。

## 不采用为真实反例：Audenaert et al. 2021

DOI：https://doi.org/10.3847/1538-3881/ac166a ，arXiv:2107.06301，第 3.8 节：

> We made a random selection of 1 000 objects from the TESS Input Catalog [...] and simulated their light curves with pure white noise on the 27.4 days Kepler time stamps.

虽然类名是 constant，但光变为模拟，因此不能冒充真实恒定星。

## 不采用为明确非变光标签：ASTRAFier 2026

arXiv:2604.07437，第 4.2 节：

> We populated the INSTRUMENT/JUNK class by selecting light curves from initial classification results that exhibited large recurring systematic trends or a lack of variability.

这是混合类别，不等同于已经确认没有天体变光的真实星。其 Kepler constant 类也沿用模拟资料。

Skarka & Henzl 2024 的南天样本也有人工审核，DOI：https://doi.org/10.1051/0004-6361/202450711 。本次北天样本已经足够，未混入南天数据。

## 可追溯材料

公开的 arXiv/Crossref 查询、论文下载回执及完整 VizieR 查询另存。主要星表来自 Harvard 镜像；Strasbourg FTP 连接超时，Strasbourg ASU 返回 404，NAOJ 镜像连接失败。失败没有解释成无星表或无变量记录。完整论文正文只保留在本地参考缓存，不重复发布；上面的短摘录和论文链接用于核对标签依据。
