import csv

# blocking locality: global > country > isp > local
# unclassified locality is named "general"
fingerprints = {
    "AE": [
        {
            "header_name": "Server",
            "header_prefix": "Protected by WireFilter",
            "locality": "country",
        }
    ],
    "AR": [
        {
            "header_full": "1.1 FC-WSA-FibertelZone3.int.fibercorp.com.ar:80 (Cisco-WSA/10.1.0-204)",
            "header_name": "Via",
            "locality": "general",
        }
    ],
    "AU": [
        {
            "header_full": "1.1 ac2106-wsag2.wsmartwifi.com.au:80 (Cisco-WSA/10.1.1-235)",
            "header_name": "Via",
            "locality": "local",
        },
        {
            "header_name": "Location",
            "header_prefix": "https://go.telstra.com.au/broadbandprotect/networkprotectionstandard",
            "locality": "isp",
        },
    ],
    "BE": [
        {
            "body_match": "that is considered illegal according to Belgian legislation",
            "locality": "country",
        },
        {
            "header_full": "1.1 webfilter.stjohns.net (http_scan_byf/3.5.16)",
            "header_name": "Via",
            "locality": "general",
        },
    ],
    "BR": [
        {
            "header_full": "1.1 wsa07.grupoamil.com.br:80 (Cisco-WSA/9.1.2-010)",
            "header_name": "Via",
            "locality": "general",
        }
    ],
    "CH": [
        {
            "header_name": "Location",
            "header_prefix": "https://192.168.88.1/sgerror.php",
            "locality": "local",
        }
    ],
    "CY": [
        {
            "body_match": "nba.com.cy/Eas/eas.nsf/All/6F7F17A7790A55C8C2257B130055C86F",
            "locality": "country",
        }
    ],
    "DE": [
        {
            "header_full": "1.1 s690-10.noc.rwth-aachen.de:80 (Cisco-WSA/10.1.1-230)",
            "header_name": "Via",
            "locality": "local",
        },
        {
            "header_full": "https://blocked.netalerts.io",
            "header_name": "X-App-Url",
            "locality": "isp",
        },
    ],
    "DK": [
        {"body_match": "lagt at blokere for adgang til siden.", "locality": "country"},
        {
            "header_full": "1.1 dsbpx001.dsb.dk:25 (Cisco-WSA/9.1.1-074)",
            "header_name": "Via",
            "locality": "country",
        },
    ],
    "EG": [
        {
            "header_name": "Location",
            "header_prefix": "http://notification.etisalat.com.eg/etisalat/notification/redirectionactions.html?",
            "locality": "isp",
        }
    ],
    "FR": [
        {"body_match": 'xtpage = "page-blocage-terrorisme"', "locality": "country"},
        {
            "header_full": "1.1 proxy2.rmc.local:80 (Cisco-WSA/9.1.1-074)",
            "header_name": "Via",
            "locality": "country",
        },
    ],
    "GB": [
        {
            "header_name": "Location",
            "header_prefix": "http://blocked.nb.sky.com",
            "locality": "isp",
        },
        {
            "header_full": "http://ee.co.uk/help/my-account/corporate-content-lock",
            "header_name": "Location",
            "locality": "local",
        },
        {
            "header_name": "Location",
            "header_prefix": "http://Filter7external.schoolsbroadband.co.uk/access",
            "locality": "local",
        },
        {
            "header_full": "www.vodafone.co.uk/contentcontrolpage/vfb-category-blocklist.html",
            "header_name": "Location",
            "locality": "isp",
        },
        {
            "header_full": "http://three.co.uk/mobilebroadband_restricted",
            "header_name": "Location",
            "locality": "isp",
        },
    ],
    "GF": [{"body_match": 'xtpage = "page-blocage-terrorisme"', "locality": "country"}],
    "GR": [
        {
            "body_match": "www.gamingcommission.gov.gr/index.php/forbidden-access-black-list/",
            "locality": "country",
        }
    ],
    "ID": [
        {
            "header_name": "Location",
            "header_prefix": "http://internet-positif.org",
            "locality": "country",
        },
        {
            "body_match": "If you find, site that you want to access does not include any of the above categories, please email to",
            "locality": "isp",
        },
    ],
    "IN": [
        # https://github.com/ooni/pipeline/issues/25#issue-154919607
        # https://explorer.ooni.org/measurement/7AEt2OwqdZUzFMzyZd3bFwnCwXp7FqYCezpaoBWdkBIfxtLtX84mXBZnlPLaTUqI?input=http:%2F%2Fthepiratebay.se
        {
            "body_match": "The page you have requested has been blocked",
            "locality": "country",
        },
        # TODO: maybe we would like to support defining a fingerprint by regexp?
        # https://github.com/ooni/pipeline/issues/25#issuecomment-487589504
        # https://explorer.ooni.org/measurement/20170915T154832Z_AS55824_qEg9opZCyJqfZJ5qFHWMR390Y1uA6eHw7j6Fx1qtU5EPE4Jnp2?input=http:%2F%2Fwww.http-tunnel.com
        {
            "header_prefix": "1.1 ironport1.iitj.ac.in:80 (Cisco-WSA/",
            "header_name": "Via",
            "locality": "local",
        },
        # https://github.com/ooni/pipeline/issues/25#issuecomment-487589504
        # https://explorer.ooni.org/measurement/20170331T050949Z_AS55824_HYIy5Ddu5UgfGq8UYBJ8aCkuz6EYAQUivivIYXDMCt6Dr6CCPU?input=http:%2F%2Fwww.babylon-x.com
        {
            "header_prefix": "1.1 ironport2.iitj.ac.in:80 (Cisco-WSA/",
            "header_name": "Via",
            "locality": "local",
        },
        # TODO this looks more like a captive portal, do we want to classify it differently?
        # https://explorer.ooni.org/measurement/20180723T000524Z_AS135201_lOpTIwn8aK4gWsbfmV9v3hlTy3ZKVYHRIA8dNBAafTxmFa6hVP?input=http:%2F%2Fwww.xbox.com
        # https://github.com/ooni/pipeline/issues/25#issuecomment-489452067
        {
            "header_full": "GoAhead-Webs",
            "header_name": "Server",
            "locality": "local",
        },
    ],
    "IR": [{"body_match": 'iframe src="http://10.10', "locality": "country"}],
    "IT": [{"body_match": "GdF Stop Page", "locality": "country"}],
    "KE": [
        {
            "header_name": "Location",
            "header_prefix": "http://159.89.232.4/alert",
            "locality": "country",
        }
    ],
    "KR": [
        {"body_match": "http://warning.or.kr", "locality": "country"},
        {
            "header_full": "http://www.warning.or.kr",
            "header_name": "Location",
            "locality": "country",
        },
    ],
    "MY": [
            # https://github.com/ooni/pipeline/issues/35#issue-169100725
            # https://explorer.ooni.org/measurement/20160802T205955Z_AS4788_3omRbM1JA9BYIMF5O5uiKEsdmUqy4kdunnKn7exzBlM2ebboDh?input=http:%2F%2Fwww.sarawakreport.org
            # TODO check if this triggers false positives, which may be the case according to: https://github.com/ooni/pipeline/issues/35#issuecomment-237997890
            {"body_match": "Makluman/Notification", "locality": "country"},

            # TODO add support for DNS based fingerprints
            # https://explorer.ooni.org/measurement/20160817T033110Z_AS4788_jk5ghw4QwieT2JOFiIqto9Z2LzCFhP05v3U0sCcaetBr50NxuU?input=http:%2F%2Fwww.sarawakreport.org%2Ftag%2F1mdb
            # {"dns_match": "175.139.142.25", "locality": "country"},
    ],
    "NO": [
        {
            "header_full": "http://block-no.altibox.net/",
            "header_name": "Location",
            "locality": "country",
        }
    ],
    "PA": [
        {
            "header_full": "1.1 barracuda.tropigas.com.pa (http_scan_byf/3.3.1)",
            "header_name": "Via",
            "locality": "country",
        }
    ],
    "PH": [
        {
            "header_name": "Location",
            "header_prefix": "http://surfalert.globe.com.ph/usedpromo?dest_url",
            "locality": "isp",
        },
        {
            "header_full": "http://cube.sunbroadband.ph:8020/balanceToOffer/init",
            "header_name": "Location",
            "locality": "isp",
        },
    ],
    "PT": [
        {
            "header_full": "http://mobilegen.vodafone.pt/denied/dn",
            "header_name": "Location",
            "locality": "isp",
        }
    ],
    "QA": [
        # https://explorer.ooni.org/measurement/bE35lS71t9vU2Swm2gxSdNPl9DWcaZpRizWrxyGEV7rh8srASwPnuwQIkdVoph0b?input=http:%2F%2Fanonym.to%2F
        # https://github.com/ooni/pipeline/issues/66#issuecomment-307233015
        {
            "header_full": "http://www.vodafone.qa/alu.cfm",
            "header_name": "Location",
            "locality": "isp",
        }
    ],
    "RO": [
        {
            "body_match": "Accesul dumneavoastr\u0103 c\u0103tre acest site a fost restric\u021bionat",
            "locality": "country",
        }
    ],
    "RU": [
        # https://explorer.ooni.org/measurement/fDYllw7vRf71n2l4g2V2ahIlPxmd6nrpsjWemcJDWX1UDN0AT5Z5uBh4HhAdFdGB?input=http:%2F%2Fthepiratebay.se%2F
        # https://github.com/ooni/pipeline/issues/26
        {
            "body_match": "Доступ к сайту ограничен в соответствии с Федеральными законами",
            "locality": "country"
        },
        {"body_match": "http://eais.rkn.gov.ru/", "locality": "country"},
        {
            "header_name": "Location",
            "header_prefix": "http://warning.rt.ru",
            "locality": "country",
        },
    ],
    "SA": [
        {
            "header_name": "Server",
            "header_prefix": "Protected by WireFilter",
            "locality": "country",
        }
    ],
    "SD": [
        {
            "header_full": "http://196.1.211.6:8080/alert/",
            "header_name": "Location",
            "locality": "country",
        }
    ],
    "SG": [
        {
            "header_full": "http://www.starhub.com:80/personal/broadband/value-added-services/safesurf/mda-blocked.html",
            "header_name": "Location",
            "locality": "country",
        }
    ],
    "TR": [
        {
            "body_match": "<title>Telekom\u00fcnikasyon \u0130leti\u015fim Ba\u015fkanl\u0131\u011f\u0131</title>",
            "locality": "country",
        }
    ],
    "US": [
        {
            "header_full": "1.1 MLD-C-Barracuda.mld.org (http_scan_byf/3.5.16)",
            "header_name": "Via",
            "locality": "country",
        },
        {
            "header_full": "1.1 forcepoint-wcg.chambersburg.localnet",
            "header_name": "Via",
            "locality": "country",
        },
        {
            "header_name": "Location",
            "header_prefix": "http://filter.esu9.org:8080/webadmin/deny/index.php",
            "locality": "country",
        },
        {
            "header_name": "Location",
            "header_prefix": "http://ibossreporter.edutech.org/block/bp.html",
            "locality": "country",
        },
        {
            "header_name": "Location",
            "header_prefix": "http://alert.scansafe.net/alert/process",
            "locality": "country",
        },
        {
            "header_name": "Location",
            "header_prefix": "http://184.168.221.96:6080/php/urlblock.php",
            "locality": "country",
        },
        {
            "header_name": "Location",
            "header_prefix": "https://gateway.wifast.com:443/wifidog/login/",
            "locality": "local",
        },
        {
            "header_name": "Location",
            "header_prefix": "https://mpswebfilterwashbu.mpls.k12.mn.us:6082/php/uid.php",
            "locality": "local",
        },
    ],
    "VN": [
        {
            "header_name": "Location",
            "header_prefix": "http://ezxcess.antlabs.com/login/index.ant?url",
            "locality": "local",
        }
    ],
    "ZZ": [
        {
            "header_full": "Kerio Control Embedded Web Server",
            "header_name": "Server",
            "locality": "local",
        },
        {
            "header_name": "Location",
            "header_prefix": "https://account.nowtv.com/broadband-buddy/blocked-pages/?domain=",
            "locality": "isp",
        },
        {
            "header_name": "Location",
            "header_prefix": "http://1.2.3.50/ups/no_access",
            "locality": "isp",
        },
        {
            "header_name": "Location",
            "header_prefix": "http://www.webscanningservice.com/WebServicesAlertPage/WebURLAlert.aspx",
            "locality": "isp",
        },
    ],
}


def read_fingerprints_csv():
    with open("fingerprints.csv", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        fingerprints = {}
        for row in reader:
            num, cc, body_match, header_name, header_prefix, header_full = row
            if cc not in fingerprints:
                fingerprints[cc] = []

            d = {}
            if body_match:
                d["body_match"] = body_match
            else:
                d["header_name"] = header_name
                if header_full:
                    d["header_full"] = header_full
                else:
                    d["header_prefix"] = header_prefix
            fingerprints[cc].append(d)
        print(fingerprints)


def mock_out_long_strings(d, maxlen):  # noqa
    # Used for debugging
    if isinstance(d, list):
        for q in d:
            mock_out_long_strings(q, maxlen)
        return
    for k, v in d.items():
        if isinstance(v, dict):
            mock_out_long_strings(v, maxlen)
        elif isinstance(v, str):
            if len(v) > maxlen:
                d[k] = "..."
        elif isinstance(v, list):
            q = v
            for v in q:
                if isinstance(v, dict):
                    mock_out_long_strings(v, maxlen)
                elif isinstance(v, str):
                    if len(v) > maxlen:
                        d[k] = "..."
