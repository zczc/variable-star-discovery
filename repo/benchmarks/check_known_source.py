"""Locate the light lost in an identified control's primary and secondary eclipses."""
from pathlib import Path
from html import escape
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from astropy.timeseries import BoxLeastSquares
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from vstar.io import read_json, write_json, sha256, now, code_fingerprint
from vstar.photometry import read_lightcurve, bin_lightcurve
from vstar.eclipse_pixels import difference_image, peak_location
from vstar.localization import localize
from vstar.reports import page


def main():
    root = Path(__file__).resolve().parents[2]
    out = root / "repo/benchmarks/source-9473243-v01"
    inputs = read_json(out / "input-manifest.json")
    assert not inputs["errors"]
    catalog = read_json(out / "tic-neighbors.json")
    response = catalog["response"]
    assert response["paging"]["pagesFiltered"] == 1 and len(response["data"]) == response["paging"]["rowsFiltered"]
    sources = response["data"]
    target = next(s for s in sources if str(s["ID"]) == "9473243")
    vsx = read_json(out / "vsx-neighbors.json")
    assert vsx["receipt"]["status"] == "completed"
    target_position = SkyCoord(target["ra"], target["dec"], unit="deg")
    neighbors = []
    for s in sources:
        if str(s["ID"]) == "9473243":
            continue
        separation = target_position.separation(SkyCoord(s["ra"], s["dec"], unit="deg")).arcsec
        neighbors.append({"tic": str(s["ID"]), "ra_deg": s["ra"], "dec_deg": s["dec"], "Tmag": s["Tmag"],
                          "sep_arcsec": float(separation), "gaia_id": s["GAIA"]})
    neighbors.sort(key=lambda n: n["sep_arcsec"])
    output = {"created_at": now(), "code_fingerprint": code_fingerprint(), "script_sha256": sha256(Path(__file__)), "input_manifest_sha256": sha256(out / "input-manifest.json"), "catalog_sha256": {name: sha256(out / name) for name in ["tic-neighbors.json", "vsx-neighbors.json"]}, "tic": "9473243", "target": target,
              "neighbors": neighbors, "vsx": vsx, "sectors": [],
              "limitations": ["No precision PRF fit or calibrated localization uncertainty.",
                              "Catalog coordinates are used as supplied; proper-motion epochs were not propagated.",
                              "Unresolved neighbors, catalog incompleteness and crowding cannot be fully ruled out.",
                              "Eclipse windows use the measured BLS period; no catalog period is injected into localization.",
                              "Conditional event scatter is descriptive, not a blind detection false-alarm probability."]}
    for obs in inputs["observations"]:
        sector = obs["sector"]
        lcpath, pixelpath = (root / obs[k]["path"] for k in ["lightcurve", "pixels"])
        for k, p in [("lightcurve", lcpath), ("pixels", pixelpath)]:
            assert sha256(p) == obs[k]["sha256"]
        saved = read_json(root / f"repo/benchmarks/known-v01/9473243-s{sector:04d}.json")
        period, duration = saved["bls"]["period_d"], saved["bls"]["duration_d"]
        lc = bin_lightcurve(read_lightcurve(lcpath), 10)
        bls = BoxLeastSquares(lc.time, lc.flux, lc.error).power(np.array([period]), np.array([duration]))
        epoch = float(bls.transit_time[0])
        phase = ((lc.time - epoch) / period) % 1
        centers = (np.arange(100) + .5) / 100
        medians = np.array([np.median(lc.flux[abs((phase - c + .5) % 1 - .5) < .015])
                            if np.any(abs((phase - c + .5) % 1 - .5) < .015) else np.nan for c in centers])
        allowed = (centers > .2) & (centers < .8) & np.isfinite(medians)
        secondary_phase = float(centers[np.flatnonzero(allowed)[np.argmin(medians[allowed])]])
        with fits.open(pixelpath, memmap=False) as h:
            table, aperture = h[1].data, np.asarray(h[2].data)
            assert h[1].header["BJDREFI"] == saved["metadata"]["BJDREFI"] and h[1].header["TIMESYS"] == "TDB"
            time, cube = np.asarray(table["TIME"], float), np.asarray(table["FLUX"], float)
            good = np.isfinite(time) & (table["QUALITY"] == 0) & np.isfinite(cube).all(axis=(1, 2))
            time, cube = time[good], cube[good]
            order = np.argsort(time)
            time, cube = time[order], cube[order]
            wcs = WCS(h[2].header)
        x0, y0 = map(float, wcs.world_to_pixel_values(target["ra"], target["dec"]))
        yy, xx = np.indices(aperture.shape)
        masks = {"pipeline_aperture": (aperture & 2) > 0,
                 "target_radius_1_pixel": np.hypot(xx - x0, yy - y0) <= 1,
                 "target_radius_2_pixels": np.hypot(xx - x0, yy - y0) <= 2}
        events, maps, aperture_depths = {}, {}, {}
        for name, ep in [("primary", epoch), ("secondary", epoch + secondary_phase * period)]:
            signal, individual, baseline, records = difference_image(time, cube, period, ep, duration)
            location = peak_location(signal)
            location["target_peak_distance_pixels"] = float(np.linalg.norm(np.array(location["peak_pixel"]) - [x0, y0]))
            location["target_core_distance_pixels"] = float(np.linalg.norm(np.array(location["positive_core_centroid"]) - [x0, y0]))
            location["events"] = records
            location["individual_core_centroids"] = [peak_location(a)["positive_core_centroid"] for a in individual]
            events[name], maps[name] = location, signal
            aperture_depths[name] = {}
            for maskname, mask in masks.items():
                baseline_flux = baseline[:, mask].sum(axis=1)
                valid = baseline_flux > 0
                depths = individual[:, mask].sum(axis=1)[valid] / baseline_flux[valid]
                aperture_depths[name][maskname] = {"pixels": int(mask.sum()), "median_fractional_drop": float(np.median(depths)),
                                                  "event_drops": depths.tolist()}
        figure, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
        for ax, name, signal in zip(axes, ["Median brightness", "Primary eclipse: missing light", "Secondary eclipse: missing light"],
                                    [np.median(cube, axis=0), maps["primary"], maps["secondary"]]):
            cmap = "magma" if name.startswith("Median") else "coolwarm"
            display = np.log10(np.maximum(signal, 1)) if name.startswith("Median") else signal
            scale = np.max(abs(display))
            im = ax.imshow(display, origin="lower", cmap=cmap, **({} if cmap == "magma" else {"vmin": -scale, "vmax": scale}))
            ax.plot(x0, y0, "o", mfc="none", mec="lime", ms=12)
            for n in neighbors:
                xn, yn = wcs.world_to_pixel_values(n["ra_deg"], n["dec_deg"])
                if -.5 <= xn < aperture.shape[1] - .5 and -.5 <= yn < aperture.shape[0] - .5:
                    ax.plot(xn, yn, "x", color="cyan", ms=4)
            if masks["pipeline_aperture"].any() and not masks["pipeline_aperture"].all():
                ax.contour(masks["pipeline_aperture"], [.5], colors="white", linewidths=.7)
            ax.set(title=name, xlabel="Pixel column", ylabel="Pixel row", xlim=(-.5, aperture.shape[1]-.5), ylim=(-.5, aperture.shape[0]-.5))
            figure.colorbar(im, ax=ax, shrink=.7, label="log10 flux (electrons/s)" if cmap == "magma" else "Missing flux (electrons/s)")
        figure.suptitle(f"TU Her / TIC 9473243 / Sector {sector}: exploratory source check")
        plot = f"sector-{sector}-difference.png"
        figure.savefig(out / plot, dpi=130)
        plt.close(figure)
        basic = localize(pixelpath, lcpath, {"ra_deg": target["ra"], "dec_deg": target["dec"], "vsx_neighbors": vsx["neighbors"]},
                         period, out / f"sector-{sector}-coherent.png")
        row = {"sector": sector, "inputs": obs, "period_from_bls_d": period, "primary_epoch_btjd_tdb": epoch,
               "window_duration_d": duration, "secondary_phase_from_data": secondary_phase, "target_pixel": [x0, y0],
               "events": events, "aperture_depths": aperture_depths, "coherent_localization": basic,
               "difference_plot": plot, "difference_plot_sha256": sha256(out / plot)}
        output["sectors"].append(row)
        print(sector, {k: (len(v["events"]), round(v["target_peak_distance_pixels"], 3), round(v["target_core_distance_pixels"], 3)) for k, v in events.items()}, flush=True)
    output["status"] = "consistent_at_tess_resolution" if all(v["target_core_distance_pixels"] < 1 for s in output["sectors"] for v in s["events"].values()) else "unresolved"
    write_json(out / "results.json", output)
    body = '<h1>已知食双星 TU Her：变暗的光来自哪里</h1><p>TIC 9473243 与 VSX 中 TU Her 相距约 0.08 角秒，TIC 对应 Gaia 编号 1333162246725509888。这里核对的是已知对象的信号来源。</p>'
    body += '<div class="notice">先保存数据、再计算。周期使用此前从光变算出的 BLS 候选值；没有把目录周期输入定位。每次食都用前后两侧的亮度估计没有发生遮挡时的光，再减去食中的光，查看少掉的光落在哪里。</div>'
    for r in output["sectors"]:
        body += f'<h2>第 {r["sector"]} 批观测</h2><img src="{r["difference_plot"]}" alt="正常亮度、深食差分和浅食差分图"><p>绿圈是目标位置，蓝叉是其他目录光点，白线是原测光区域。左图表示平常收到的光；中、右图的红色表示遮挡期间减少的光。两种食分别统计，不用正常图的最亮位置代替变光来源。</p>'
        body += '<table><tr><th>变化</th><th>可用事件数</th><th>变化中心距目标（像素）</th><th>原测光区域的典型下降比例</th></tr>'
        for name, label in [("primary", "深食"), ("secondary", "浅食")]:
            e = r["events"][name]
            body += f'<tr><td>{label}</td><td>{len(e["events"])}</td><td>{e["target_core_distance_pixels"]:.3f}</td><td>{r["aperture_depths"][name]["pipeline_aperture"]["median_fractional_drop"]:.1%}</td></tr>'
        body += '</table><p>中心是在最强变化附近 3×3 像素中估计，未做精细的光斑拟合。下降比例先对每次事件窗口内的光取平均，再取各事件下降比例的中位数，不是精确最大变幅。</p>'
    conclusion = "两个时段的深食、浅食都支持变化来自目标附近。" if output["status"] == "consistent_at_tess_resolution" else "本轮尚不能确定变化来自目标。"
    body += f'<h2>本次结论</h2><p>{conclusion}</p><p>这项检查只支持或质疑 TESS 分辨率下的来源位置。还不能排除未分辨的近邻，也没有给出正式定位误差。目录坐标未按自行传播到每个观测时刻；三种测光区域都能看到深食和浅食。它们共享像素和观测噪声，不是三套独立证据。完整结果保留各区域的事件下降比例，可用于进一步复核。</p><p><a href="results.json">完整结果与局限</a> · <a href="tic-neighbors.json">TIC 邻域查询</a> · <a href="vsx-neighbors.json">VSX 身份记录</a></p>'
    (out / "index.html").write_text(page("TU Her 信号来源检查", body))
    print("SOURCE_CHECK_COMPLETE", output["status"], flush=True)


if __name__ == "__main__":
    main()
