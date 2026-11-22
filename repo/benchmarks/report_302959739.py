"""Build the candidate report from saved results; no search or threshold changes."""
from html import escape
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from followup_302959739 import ROOT, RUN, verify_inputs
from vstar.io import now, read_json, sha256, write_json
from vstar.reports import page


def build():
    verified = verify_inputs()
    row = read_json(RUN / 'combined-seven-sectors.json')
    decision = read_json(RUN / 'combined-adjudication.json')
    diagnostic = read_json(RUN / 'transient-diagnostic/diagnostic.json')
    prior = read_json(RUN / 'plan.json')['prior_period_d']
    sectors = []
    aliases = []
    for obs in sorted(row['observations'], key=lambda x: x['sector']):
        r = {'sector': obs['sector'], 'new_observation': obs['sector'] not in (10, 39)}
        for name, product in obs['products'].items():
            result = product['result']
            r[name] = {k: result[k] for k in ('periodic_detected', 'photometric_period_d', 'selected_period_d', 'period_status')}
            for factor in (.5, 1, 2):
                pool = [c for c in result['candidates'] if abs(c['period_d']/(prior*factor)-1) < .01]
                aliases.append({'sector': obs['sector'], 'product': name, 'factor_of_prior': factor,
                                'candidate': max(pool, key=lambda c: c['gain']) if pool else None})
        sectors.append(r)
    write_json(RUN / 'period-comparison.json', {'created_at': now(), 'prior_period_d': prior,
        'method': 'Select the highest saved predictive gain within 1% of P/2, P, 2P. No new search. Absence is not rejection.',
        'rows': aliases, 'limitation': 'A repeated photometric pattern does not alone establish the physical rotation or orbital period.'})
    localization = []
    for sec in (10, 39, 36):
        r = read_json(RUN / f'localization-verified/s{sec}.json')
        allfit = r['fits']['period_all']['free_fit']
        for fit in r['fits'].values():
            assert fit['free_fit']['optimizer_success'] and not fit['free_fit']['search_boundary']
        assert all(x['optimizer_success'] and not x['boundary'] for x in r['registration'])
        sensitivity = [s for f in r['fits'].values() for s in f['free_fit']['registration_sensitivity']]
        localization.append({'sector': sec, 'all_period_map_target_offset_px': allfit['distance_to_target_pixel'],
            'all_period_map_neighbor_offset_px': allfit['distance_to_neighbor_pixel'],
            'all_reported_variants_closer_to_target': all(x['distance_to_target_pixel'] < x['distance_to_neighbor_pixel'] for x in sensitivity),
            'source_confirmed': False})
    summary = {'created_at': now(), 'tic': '302959739', 'prior_period_d': prior,
        'new_lightcurve_sectors': [11, 12, 36, 37, 38], 'pixel_sectors': [10, 39, 36],
        'PDCSAP_epochs_detected': sum(x['PDCSAP']['periodic_detected'] for x in sectors),
        'total_epochs': len(sectors), 'sectors': sectors, 'original_combined_decision': decision,
        'source_diagnostics': localization,
        'post_hoc_masked_s36': {k: diagnostic[k] for k in ('post_hoc', 'original_detection_replaced', 'excluded_cadences', 'valid_cadences')},
        'source_interpretation': 'PRF diagnostics favor the target; real-sky model errors remain uncalibrated and the close neighbor is not conclusively excluded.',
        'status': 'priority_candidate_source_and_novelty_unconfirmed',
        'source_confirmed': False, 'novelty_confirmed': False, 'submission_ready': False,
        'input_verification': verified}
    write_json(RUN / 'summary.json', summary)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout='constrained')
    for ax, sec in zip(axes, (10, 39, 36)):
        r = read_json(RUN / f'localization-verified/s{sec}.json')
        origin = np.array(r['target_pixel']) + r['registration'][1]['shift_pixel']
        neighbor = np.array(r['neighbor_pixel']) - np.array(r['target_pixel'])
        ax.scatter(0, 0, marker='o', s=100, facecolors='none', edgecolors='green', label='Gaia target')
        ax.scatter(*neighbor, marker='x', s=80, color='purple', label='Gaia neighbor')
        markers = {'period_all': 'o', 'period_event_masked': 's', 'period_first_half': '^', 'period_second_half': 'v', 'transient': '*'}
        for label, fit in r['fits'].items():
            delta = np.array(fit['free_fit']['xy']) - origin
            ax.scatter(*delta, marker=markers[label], s=45 if label != 'transient' else 110,
                       label=label.replace('period_', '').replace('_', ' '), alpha=.8)
        ax.set(xlim=(-.17, .35), ylim=(-.2, .35), title=f'Sector {sec}',
               xlabel='Column offset (pixel)', ylabel='Row offset (pixel)')
        ax.set_aspect('equal'); ax.grid(alpha=.2)
    axes[-1].legend(fontsize=7, loc='upper left', bbox_to_anchor=(1.02, 1))
    fig.suptitle('Exploratory PRF positions; dots are fits, not uncertainty regions')
    fig.savefig(RUN / 'localization-comparison.png', dpi=150); plt.close(fig)

    def period_cell(value):
        p = value['photometric_period_d']
        return ('未检出' if p is None else f'{p:.8f} 天') + '；' + escape(value['period_status'])

    body = '<h1>TIC 302959739：追加观测与来源诊断</h1>'
    body += '<p>2026-11-22。当前保留为优先核验候选，未确认来源或首次发现资格，也未投稿。</p>'
    body += '<div class="notice">7 段原始观测中，6 段 PDCSAP 检出约 0.4377 天变化；S36 未通过。冻结规则合并后仍为 unresolved，没有最终周期。事后屏蔽不能改写这个结果。</div>'
    body += '<h2>原始结果</h2><table><tr><th>观测区</th><th>SAP</th><th>PDCSAP</th></tr>'
    for s in sectors:
        body += f'<tr><td>S{s["sector"]}（{"新增" if s["new_observation"] else "复用"}）</td><td>{period_cell(s["SAP"])}</td><td>{period_cell(s["PDCSAP"])}</td></tr>'
    body += '</table><p>S12 检出但保留竞争周期；S39 的 SAP 选了 6.5674 天，PDCSAP 选了约 0.4376 天。没有隐藏产品分歧。</p>'
    body += '<p><a href="../../benchmarks/scale-validation-v01/evaluation/tic-302959739/period/index.html">复用的 S10／S39 原报告</a> · <a href="visual-review.json">本轮看图备注</a></p>'
    body += '<p>约 0.2188 天半周期在全部 7 段 PDCSAP 中不合格；约 0.8754 天倍周期在同样 6 段中合格。倍周期能容纳两个相似周期，不能因此确定物理自转或轨道周期。当前也没有跨年相位连接或正式周期误差。</p>'
    body += '<h2>S36 强突增的事后诊断</h2><p>按 PDCSAP 距中值超过 8 × 1.4826 × MAD 屏蔽 114／15,679 个有效采样点，两产品共用这个掩码，通量值不改。SAP 和 PDCSAP 都恢复约 0.437909 天；单段恢复不等于原始全时段裁定通过。剩余突增尾部和趋势仍可见。</p>'
    body += '<p>增亮最高有效采样发生在 BTJD 2296.910554（BJD_TDB − 2457000），相对各自整段中值的 SAP／PDCSAP 通量分别增加约 291%／478%。这是不同产品的相对通量，受混光和校正影响，不是去混光后的本征耀发幅度。</p>'
    body += '<p><a href="new-periods/s0036-products.png">原始 S36 图</a> · <a href="transient-diagnostic/products/s0036-products.png">屏蔽后的图</a> · <a href="transient-diagnostic/diagnostic.json">完整掩码与结果</a></p>'
    body += '<h2>目标与 5.09 角秒近邻</h2><img src="localization-comparison.png" alt="三段观测的目标、近邻和信号拟合位置">'
    body += '<p>使用 Gaia 自行传播位置、官方 TESS 像素响应模型及全场非负光度拟合校准坐标。3 段完整周期图距目标约 0.0795、0.0194、0.0632 像素，距近邻约 0.2196、0.2703、0.2178 像素。S36 短时增亮距目标约 0.0101 像素、距近邻约 0.2691 像素。不同校准设置、去除突增以及前后半段均更靠近目标。</p>'
    body += '<p>这些数字是模型拟合偏移，不是定位误差或置信区间。中位场图有结构性残差，模型失配、颜色、场外源和缺失自行均可带来系统偏移；混合变光源也未被完整建模。仅改变场图权重的 4 个设置不能覆盖全部系统误差。当前支持目标附近来源，尚不能彻底排除近邻；S36 固定参考周期图也不算独立检出。</p>'
    for sec in (10, 39, 36):
        body += f'<p><a href="localization-verified/s{sec}.json">S{sec} 完整拟合</a></p><img src="localization-verified/s{sec}-diagnostics.jpg" alt="S{sec} 场图、残差和周期来源图">'
    body += '<h2>核验与复现</h2><p>5 项数值测试通过；同一官方 PRF 的目标／近邻注入共 6 项恢复检查通过。这只验证代码，不能校准实天误差。5 段新增光变重算与保存数字一致，3 段来源图重算一致。7,041 个基线文件校验通过，科学检测源码保持原指纹。</p>'
    body += '<p><a href="verification.json">复算核验</a> · <a href="summary.json">完整摘要</a> · <a href="period-comparison.json">半／倍周期比较</a> · <a href="acquisition.json">原始数据回执</a> · <a href="plan.json">读取新光变前的方案</a> · <a href="prf-reference/LICENSE">PRF 适配器 MIT 许可</a></p>'
    body += '<p>下一步：用独立实天来源或可分辨的测光校准近邻排除能力，继续核查年轻星、自转及耀发研究中的先前报告，再确定物理分类、周期误差和历元。本轮没有新增目录查重结论；11 月 20 日的查询覆盖边界仍有效。</p>'
    body += '<h2>各新增区原图</h2>'
    for sec in (11, 12, 36, 37, 38):
        body += f'<h3>S{sec}</h3><img src="new-periods/s{sec:04d}-products.png" alt="第 {sec} 区两测光产品的原始曲线与折叠图">'
    (RUN / 'index.html').write_text(page('TIC 302959739 追加核验', body))
    files = [p for p in RUN.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name != 'manifest.json']
    write_json(RUN / 'manifest.json', {'created_at': now(), 'files': [
        {'path': str(p.relative_to(ROOT)), 'sha256': sha256(p), 'bytes': p.stat().st_size} for p in sorted(files)]})
    print(f'Report built: {len(files)} archived files; no detector outputs changed.')


if __name__ == '__main__':
    build()
