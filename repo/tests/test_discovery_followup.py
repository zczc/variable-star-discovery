from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
import followup_discovery_catalogs as followup
import report_discovery_followup as report


HEADERS = ['ASAS-SN Name', 'Other Names', 'Right Ascension', 'Declination',
           'Distance from Search (arcsec)', 'Mean VMag', 'Amplitude', 'Period', 'Type']


def test_asassn_header_without_tr_and_explicit_empty_result():
    html = '<table><thead>' + ''.join('<th>' + h + '</th>' for h in HEADERS)
    html += '</thead><tbody></tbody></table>No Variables found<div class="page-item next disabled">'
    assert followup.parse_asassn(html)['rows'] == []
    with pytest.raises(ValueError):
        followup.parse_asassn(html.replace('No Variables found', ''))
    with pytest.raises(ValueError):
        followup.parse_asassn('<html>Service unavailable</html>')


def test_asassn_known_variable_is_retained():
    html = '<table><thead><tr>' + ''.join('<th>' + h + '</th>' for h in HEADERS)
    html += '</tr></thead><tbody><tr>'
    values = ['<a href="/variables/abc">ASASSN-V Test</a>', '', '10', '20', '.17', '15', '1', '1.54', 'EA']
    html += ''.join('<td>' + v + '</td>' for v in values) + '</tr></tbody></table>'
    result = followup.parse_asassn(html)
    assert result['rows'][0]['Type'] == 'EA'
    assert result['detail_links'] == ['/variables/abc']


def test_gaia_source_ids_keep_integer_precision_and_errors_are_not_empty():
    body = 'source_id,ra,dec,pmra,pmdec,phot_variable_flag,best_class_name\n5221068695785400576,125,-72,0,0,VARIABLE,DSCT|GDOR|SXPHE\n'
    assert followup.parse_gaia(body)['rows'][0]['source_id'] == '5221068695785400576'
    with pytest.raises(ValueError):
        followup.parse_gaia('<VOTABLE><INFO name="QUERY_STATUS" value="ERROR"/></VOTABLE>')


def test_vizier_unavailable_catalog_is_not_no_match():
    for body in ('#RESOURCE=\n#Name:\n', '#INFO\tError=Table or Catalog not found\n'):
        with pytest.raises(ValueError):
            report.vizier_rows({'http_status': 200, 'body': body}, 'J/ApJS/268/4/table1')


def test_scientific_notation_tic_and_gaia_tap_error():
    assert report.normalized_tic(2.8763697e8) == '287636970'
    with pytest.raises(ValueError):
        report.normalized_tic(123.5)
    with pytest.raises(ValueError):
        report.tap_rows({'http_status': 200, 'body': '{"error":"unavailable"}'})
