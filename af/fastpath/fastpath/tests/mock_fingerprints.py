fingerprints = {
    "ZZ": {
        "body_match": [],
        "header_prefix": [
            {"header_name": "location", "header_prefix": "http://1.2.3.50/ups/no_access", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "http://www.webscanningservice.com/WebServicesAlertPage/WebURLAlert.aspx",
                "locality": "isp",
            },
        ],
        "header_full": [
            {"header_name": "server", "header_full": "Barracuda/NGFirewall", "locality": "local"},
            {"header_name": "server", "header_full": "BarracudaHTTP 4.0", "locality": "local"},
        ],
        "dns_full": [
            {"dns_full": "185.228.168.254", "locality": "general"},
            {"dns_full": "207.246.127.171", "locality": "general"},
            {"dns_full": "45.77.77.148", "locality": "general"},
            {"dns_full": "185.236.104.104", "locality": "general"},
            {"dns_full": "54.242.237.204", "locality": "general"},
            {"dns_full": "45.32.203.129", "locality": "general"},
            {"dns_full": "3.93.224.57", "locality": "general"},
            {"dns_full": "52.206.227.167", "locality": "general"},
            {"dns_full": "195.46.39.11", "locality": "local"},
        ],
    },
    "AE": {
        "header_prefix": [
            {"header_name": "server", "header_prefix": "Protected by WireFilter", "locality": "country"},
            {
                "header_name": "location",
                "header_prefix": "http://www.bluecoat.com/notify-NotifyUser1",
                "locality": "country",
            },
            {"header_name": "location", "header_prefix": "http://lighthouse.du.ae", "locality": "isp"},
        ],
        "body_match": [{"body_match": "it-security-operations@etisalat.ae", "locality": "isp"}],
    },
    "AF": {
        "body_match": [
            {
                "body_match": 'content="Access Denied - Afghan Wireless Communication Company',
                "locality": "isp",
            }
        ]
    },
    "AR": {
        "body_match": [
            {"body_match": "<title>Notificación: política: filtrado de URL</title>", "locality": "isp"}
        ]
    },
    "AU": {
        "body_match": [
            {"body_match": "<title>Notification: Policy: URL Filtering</title>", "locality": "local"},
            {"body_match": "Blocked by ContentKeeper", "locality": "isp"},
        ],
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "https://go.telstra.com.au/broadbandprotect/networkprotectionstandard",
                "locality": "isp",
            }
        ],
    },
    "BE": {
        "body_match": [
            {
                "body_match": "that is considered illegal according to Belgian legislation",
                "locality": "country",
            }
        ],
        "header_full": [
            {
                "header_full": "1.1 webfilter.stjohns.net (http_scan_byf/3.5.16)",
                "header_name": "via",
                "locality": "local",
            }
        ],
    },
    "BR": {
        "header_full": [
            {
                "header_full": "1.1 wsa07.grupoamil.com.br:80 (Cisco-WSA/9.1.2-010)",
                "header_name": "via",
                "locality": "local",
            },
            {"header_full": "SonicWALL", "header_name": "server", "locality": "local"},
        ]
    },
    "BH": {
        "body_match": [
            {"body_match": "www.anonymous.com.bh", "locality": "isp"},
            {"body_match": "www.viva.com.bh/static/block", "locality": "isp"},
            {"body_match": "menatelecom.com/deny_page.html", "locality": "isp"},
        ]
    },
    "BY": {
        "header_prefix": [
            {"header_name": "location", "header_prefix": "https://www.a1.by/mininfo/", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://82.209.230.23", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "https://internet.mts.by/blocked/",
                "locality": "isp",
            },
            {
                "header_name": "location",
                "header_prefix": "https://vk.com/blank.php?rkn=",
                "locality": "country",
            },
        ],
        "dns_full": [{"dns_full": "134.17.0.7", "locality": "isp"}],
    },
    "CA": {
        "body_match": [
            {"body_match": " <title>Notification: Policy: URL Filtering</title>", "locality": "local"},
            {
                "body_match": "Access to this site has been blocked by an Order issued by the Federal Court of Canada",
                "locality": "isp",
            },
            {
                "body_match": "Access to the location you have attempted to reach has been disabled pursuant to an Order&nbsp;of the Federal Court (Canada)",
                "locality": "isp",
            },
        ]
    },
    "CH": {
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "https://192.168.88.1/sgerror.php",
                "locality": "local",
            }
        ]
    },
    "CL": {
        "header_full": [
            {"header_full": "Kerio Control Embedded Web Server", "header_name": "server", "locality": "local"}
        ]
    },
    "CO": {
        "body_match": [
            {
                "body_match": "Esta página ha sido bloqueada por disposición del Ministerio de las TIC,",
                "locality": "country",
            }
        ]
    },
    "CY": {
        "body_match": [
            {
                "body_match": "nba.com.cy/Eas/eas.nsf/All/6F7F17A7790A55C8C2257B130055C86F",
                "locality": "country",
            }
        ]
    },
    "CN": {
        "dns_full": [
            {"dns_full": "8.7.198.45", "locality": "country"},
            {"dns_full": "37.61.54.158", "locality": "country"},
            {"dns_full": "46.82.174.68", "locality": "country"},
            {"dns_full": "78.16.49.15", "locality": "country"},
            {"dns_full": "93.46.8.89", "locality": "country"},
            {"dns_full": "159.106.121.75", "locality": "country"},
            {"dns_full": "203.98.7.65", "locality": "country"},
            {"dns_full": "59.24.3.173", "locality": "country"},
            {"dns_full": "203.98.7.65", "locality": "country"},
            {"dns_full": "243.185.187.39", "locality": "country"},
        ]
    },
    "DE": {
        "body_match": [
            {"body_match": "<title>Notification: Policy: URL Filtering</title>", "locality": "local"},
            {"body_match": "title>IServ", "locality": "local"},
        ],
        "header_full": [
            {"header_full": "https://blocked.netalerts.io", "header_name": "x-app-url", "locality": "isp"}
        ],
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "https://hotspot.vodafone.de/access_denied.html",
                "locality": "isp",
            }
        ],
    },
    "DK": {
        "body_match": [
            {"body_match": "lagt at blokere for adgang til siden.", "locality": "country"},
            {"body_match": "<title>Notification: Policy: URL Filtering</title>", "locality": "local"},
        ]
    },
    "EG": {
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "http://notification.etisalat.com.eg/etisalat/notification/redirectionactions.html?",
                "locality": "isp",
            }
        ]
    },
    "ES": {
        "body_match": [{"body_match": "<title>Dominio-No-Disponible</title>", "locality": "global"}],
        "header_full": [{"header_name": "server", "header_full": "V2R2C00-IAE/1.0", "locality": "local"}],
    },
    "FR": {
        "body_match": [
            {"body_match": 'xtpage = "page-blocage-terrorisme"', "locality": "country"},
            {"body_match": "<title>Notification: Policy: URL Filtering</title>", "locality": "local"},
        ],
        "header_prefix": [{"header_name": "server", "header_prefix": "Olfeo", "locality": "local"}],
    },
    "GB": {
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "http://assets.o2.co.uk/18plusaccess/",
                "locality": "isp",
            },
            {
                "header_name": "location",
                "header_prefix": "http://www.vodafone.co.uk/restricted-content",
                "locality": "isp",
            },
            {
                "header_name": "location",
                "header_prefix": "https://www.giffgaff.com/mobile/over18",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "http://block.cf.sky.com", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://blocked.nb.sky.com", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "http://Filter7external.schoolsbroadband.co.uk/access",
                "locality": "isp",
            },
            {
                "header_name": "location",
                "header_prefix": "https://account.nowtv.com/broadband-buddy/blocked-pages/",
                "locality": "isp",
            },
        ],
        "body_match": [
            {
                "body_match": "Taunton School allow access to the following search engines",
                "locality": "local",
            },
            {
                "body_match": '<a href="https://smobile.three.co.uk/837/">Age Validation</a>',
                "locality": "isp",
            },
        ],
        "header_full": [
            {
                "header_full": "http://ee.co.uk/help/my-account/corporate-content-lock",
                "header_name": "location",
                "locality": "isp",
            },
            {
                "header_full": "www.vodafone.co.uk/contentcontrolpage/vfb-category-blocklist.html",
                "header_name": "location",
                "locality": "isp",
            },
            {
                "header_full": "http://three.co.uk/mobilebroadband_restricted",
                "header_name": "location",
                "locality": "isp",
            },
        ],
    },
    "GF": {"body_match": [{"body_match": 'xtpage = "page-blocage-terrorisme"', "locality": "country"}]},
    "GR": {
        "body_match": [
            {
                "body_match": "www.gamingcommission.gov.gr/index.php/forbidden-access-black-list/",
                "locality": "country",
            }
        ],
        "header_prefix": [
            {"header_prefix": "http://1.2.3.50/ups/no_access", "header_name": "location", "locality": "isp"}
        ],
    },
    "HU": {
        "body_match": [
            {"body_match": "<title>Oops! Website blocked!</title>", "locality": "local"},
            {"body_match": "<title>Web Page Blocked</title>", "locality": "local"},
        ]
    },
    "ID": {
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "http://internet-positif.org",
                "locality": "country",
            },
            {
                "header_name": "location",
                "header_prefix": "http://internetpositif.uzone.id",
                "locality": "country",
            },
            {"header_name": "location", "header_prefix": "http://mercusuar.uzone.id/", "locality": "country"},
            {"header_name": "location", "header_prefix": "http://filter.citra.net.id", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://block.myrepublic.co.id", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "https://internetbaik.telkomsel.com/block?",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "https://blockpage.xl.co.id", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://restricted.tri.co.id", "locality": "isp"},
        ],
        "body_match": [
            {"body_match": "http://block.uzone.id", "locality": "country"},
            {"body_match": ".uzone.id/assets/internetpositif", "locality": "country"},
            {"body_match": "positif.uzone.id", "locality": "country"},
            {
                "body_match": "This page is blocked by <a href=http://trustpositif.kominfo.go.id",
                "locality": "country",
            },
            {
                "body_match": "tidak bisa diakses melalui jaringan ini sesuai peraturan perundang-undangan",
                "locality": "country",
            },
            {"body_match": "internetpositif.mncplaymedia.com", "locality": "isp"},
            {
                "body_match": "Maaf, akses Anda ke situs ini telah diblokir sesuai dengan <a",
                "locality": "isp",
            },
            {
                "body_match": "We are blocking this abusive site as stated by the Indonesia regulation in order to provide Internet Sehat.",
                "locality": "isp",
            },
            {"body_match": "internetsehatdanamanfastnet.html", "locality": "isp"},
            {"body_match": "var pname='internet-sehat';", "locality": "isp"},
            {"body_match": "xblock.gmedia.net.id", "locality": "isp"},
            {"body_match": "http://crypto.net.id/images/crypto_emblem.png", "locality": "isp"},
            {"body_match": "<title>Negatif Konten</title>", "locality": "isp"},
            {
                "body_match": "<a href=http://megavision.net.id>StarNet Project</a></strong> - DNS Filter Project.",
                "locality": "isp",
            },
            {"body_match": "<h2>INTERNET SEHAT CITRANET</h2>", "locality": "isp"},
            {"body_match": "<title>Indosatooredoo Netsafe</title>", "locality": "isp"},
            {"body_match": "<title>Netsafe IndosatM2</title>", "locality": "isp"},
            {"body_match": "http://netsafe.indosatooredoo.com", "locality": "isp"},
            {"body_match": "argon_files/stop.jpg", "locality": "isp"},
            {"body_match": "https://myrepublic.co.id/internet-sehat/", "locality": "isp"},
            {"body_match": "internetbaik.telkomsel.com/", "locality": "isp"},
            {"body_match": "telkomsel|internet sehat|baik|internet baik", "locality": "isp"},
            {"body_match": "www.xl.co.id/xlblockpage", "locality": "isp"},
            {"body_match": "blockpage.xl.co.id", "locality": "isp"},
            {"body_match": "www.biznetnetworks.com/safesurf/", "locality": "isp"},
            {"body_match": "VELO Networks :: Internet Sehat dan Aman", "locality": "isp"},
            {"body_match": "restricted.tri.co.id/", "locality": "isp"},
            {"body_match": "<title>IdOLA Lintasarta</title>", "locality": "isp"},
            {"body_match": "<title>Internet Sehat Telkom University</title>", "locality": "local"},
            {"body_match": "<title>Blocked Page Bina Nusantara Networks</title>", "locality": "isp"},
            {"body_match": "di.og.ofnimok@netnoknauda", "locality": "country"},
        ],
        "dns_full": [
            {"dns_full": "180.131.146.7", "locality": "general"},
            {"dns_full": "202.3.219.209", "locality": "isp"},
            {"dns_full": "restricted.tri.co.id", "locality": "isp"},
            {"dns_full": "116.206.10.31", "locality": "isp"},
            {"dns_full": "36.86.63.185", "locality": "isp"},
            {"dns_full": "internet-positif.org", "locality": "isp"},
            {"dns_full": "mypage.blocked.bltsel", "locality": "isp"},
            {"dns_full": "114.121.254.4", "locality": "isp"},
            {"dns_full": "180.214.232.61", "locality": "isp"},
            {"dns_full": "202.62.29.1", "locality": "isp"},
            {"dns_full": "103.47.132.195", "locality": "isp"},
            {"dns_full": "internetsehataman.cbn.net.id", "locality": "isp"},
            {"dns_full": "blockpage.xl.co.id", "locality": "isp"},
            {"dns_full": "202.52.141.98", "locality": "isp"},
            {"dns_full": "150.107.140.200", "locality": "isp"},
            {"dns_full": "103.14.16.18", "locality": "isp"},
            {"dns_full": "113.197.108.236", "locality": "isp"},
            {"dns_full": "202.65.113.54", "locality": "isp"},
            {"dns_full": "103.195.19.54", "locality": "isp"},
            {"dns_full": "103.10.120.3", "locality": "isp"},
            {"dns_full": "27.123.220.197", "locality": "isp"},
            {"dns_full": "103.108.159.238", "locality": "isp"},
            {"dns_full": "103.126.10.252", "locality": "isp"},
            {"dns_full": "103.142.60.250", "locality": "isp"},
            {"dns_full": "103.19.56.2", "locality": "isp"},
            {"dns_full": "103.70.68.68", "locality": "isp"},
            {"dns_full": "103.83.96.242", "locality": "isp"},
            {"dns_full": "114.129.22.33", "locality": "isp"},
            {"dns_full": "114.129.23.9", "locality": "isp"},
            {"dns_full": "netsafe.indosatm2.com", "locality": "isp"},
            {"dns_full": "114.6.128.8", "locality": "isp"},
            {"dns_full": "150.107.151.151", "locality": "isp"},
            {"dns_full": "158.140.186.3", "locality": "isp"},
            {"dns_full": "internetpositif3.firstmedia.com", "locality": "isp"},
            {"dns_full": "filter.melsa.net.id", "locality": "isp"},
            {"dns_full": "block.centrin.net.id", "locality": "isp"},
            {"dns_full": "202.152.4.67", "locality": "isp"},
            {"dns_full": "202.165.36.253", "locality": "isp"},
            {"dns_full": "202.169.44.80", "locality": "isp"},
            {"dns_full": "202.50.202.50", "locality": "isp"},
            {"dns_full": "trustpositif.iforte.net.id", "locality": "isp"},
            {"dns_full": "202.56.160.131", "locality": "isp"},
            {"dns_full": "202.56.160.132", "locality": "isp"},
            {"dns_full": "203.99.130.131", "locality": "isp"},
            {"dns_full": "203.119.13.75", "locality": "isp"},
            {"dns_full": "203.119.13.76", "locality": "isp"},
            {"dns_full": "203.160.56.38", "locality": "isp"},
            {"dns_full": "220.247.168.195", "locality": "isp"},
            {"dns_full": "58.147.184.141", "locality": "isp"},
            {"dns_full": "58.147.185.131", "locality": "isp"},
            {"dns_full": "202.73.99.3", "locality": "isp"},
            {"dns_full": "xblock.gmedia.net.id", "locality": "isp"},
            {"dns_full": "49.128.177.13", "locality": "isp"},
            {"dns_full": "internetsehat.smartfren.com", "locality": "isp"},
            {"dns_full": "internetpositif.mncplaymedia.com", "locality": "isp"},
            {"dns_full": "dnssehat.telkomuniversity.ac.id", "locality": "isp"},
            {"dns_full": "trustpositif.kominfo.go.id", "locality": "country"},
        ],
    },
    "IE": {
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "https://m.three.ie/adult-content",
                "locality": "isp",
            }
        ]
    },
    "IL": {"body_match": [{"body_match": "http://mobile.netsparkmobile.com/?a=block", "locality": "isp"}]},
    "IN": {
        "body_match": [
            {"body_match": "The page you have requested has been blocked", "locality": "country"},
            {"body_match": "http://www.airtel.in/dot/?dpid=", "locality": "isp"},
        ],
        "header_prefix": [
            {
                "header_prefix": "1.1 ironport1.iitj.ac.in:80 (Cisco-WSA/",
                "header_name": "via",
                "locality": "local",
            },
            {
                "header_prefix": "1.1 ironport2.iitj.ac.in:80 (Cisco-WSA/",
                "header_name": "via",
                "locality": "local",
            },
        ],
        "header_full": [{"header_full": "GoAhead-Webs", "header_name": "server", "locality": "local"}],
    },
    "IR": {
        "body_match": [
            {"body_match": 'iframe src="http://10.10', "locality": "country"},
            {
                "body_match": '</title></head><body><iframe src="http://[d0:0:0:0:0:0:0:11:80]" style="width: 100%; height: 100%" scrolling="no" marginwidth="0" marginheight="0" frameborder="0" vspace="0" hspace="0"></iframe></body></html>',
                "locality": "country",
            },
            {"body_match": "internet.ir/1-2", "locality": "country"},
            {"body_match": "peyvandha.ir/1-2", "locality": "country"},
        ],
        "dns_full": [
            {"dns_full": "10.10.34.34", "locality": "country"},
            {"dns_full": "10.10.34.35", "locality": "country"},
            {"dns_full": "10.10.34.36", "locality": "country"},
            {"dns_full": "d0::11", "locality": "country"},
        ],
    },
    "IT": {
        "body_match": [{"body_match": "GdF Stop Page", "locality": "country"}],
        "header_full": [
            {"header_name": "server", "header_full": "V2R2C00-IAE/1.0", "locality": "local"},
            {"header_full": "WebProxy/1.0 Pre-Alpha", "header_name": "server", "locality": "local"},
        ],
    },
    "KR": {
        "body_match": [
            {"body_match": "cm/cheongshim/img/cheongshim_block.png", "locality": "local"},
            {"body_match": "http://warning.or.kr", "locality": "country"},
            {"body_match": "cleanmobile01.nate.com", "locality": "isp"},
            {"body_match": "cleanmobile02.nate.com", "locality": "isp"},
            {"body_match": "<title>청소년 유해차단서비스</title>", "locality": "isp"},
        ],
        "header_full": [
            {"header_full": "http://www.warning.or.kr", "header_name": "location", "locality": "country"}
        ],
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "http://cleanweb1.uplus.co.kr/kren",
                "locality": "isp",
            }
        ],
    },
    "KG": {
        "header_full": [
            {
                "header_name": "location",
                "header_full": "http://homeline.kg/access/blockpage.html",
                "locality": "isp",
            }
        ]
    },
    "KW": {
        "header_prefix": [
            {"header_name": "location", "header_prefix": "http://restrict.kw.zain.com", "locality": "isp"}
        ],
        "body_match": [
            {"body_match": "blocked.fasttelco.net/?dpid=", "locality": "isp"},
            {"body_match": "http://pay.viva.com.kw/images/access-en.jpg", "locality": "isp"},
        ],
    },
    "MM": {
        "header_prefix": [
            {"header_name": "location", "header_prefix": "http://notice.myanmarnet.com", "locality": "isp"}
        ],
        "body_match": [
            {
                "body_match": '<li><a href="whatever.html" class="menupics"><img src="legaltext.png" alt="descriptivetext" /></a></li>',
                "locality": "isp",
            }
        ],
        "dns_full": [
            {"dns_full": "59.153.90.11", "locality": "isp"},
            {"dns_full": "167.172.4.60", "locality": "country"},
        ],
    },
    "MN": {"dns_full": [{"dns_full": "218.100.84.78", "locality": "country"}]},
    "MX": {"header_full": [{"header_name": "server", "header_full": "V2R2C00-IAE/1.0", "locality": "local"}]},
    "MY": {
        "body_match": [{"body_match": "Makluman/Notification", "locality": "country"}],
        "header_prefix": [
            {"header_name": "location", "header_prefix": "https://wifi.uitm.edu.my", "locality": "local"}
        ],
        "dns_full": [{"dns_full": "175.139.142.25", "locality": "country"}],
    },
    "NO": {
        "header_full": [
            {"header_full": "http://block-no.altibox.net/", "header_name": "location", "locality": "country"}
        ]
    },
    "NP": {
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "http://blockdomain.worldlink.com.np",
                "locality": "isp",
            }
        ],
        "body_match": [{"body_match": "nta.gov.np/en/notice-regarding-site-block", "locality": "isp"}],
    },
    "OM": {
        "body_match": [
            {"body_match": "block.om/newrequestform.aspx?accessurl=", "locality": "isp"},
            {"body_match": "http://siteblocked.om/?accessurl=", "locality": "isp"},
        ]
    },
    "PA": {
        "body_match": [{"body_match": "<p>Redirecting you to Barracuda Web Filter.</p>", "locality": "local"}]
    },
    "PH": {
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "http://surfalert.globe.com.ph/usedpromo?dest_url",
                "locality": "isp",
            }
        ],
        "header_full": [
            {
                "header_full": "http://cube.sunbroadband.ph:8020/balanceToOffer/init",
                "header_name": "location",
                "locality": "isp",
            }
        ],
    },
    "PK": {
        "header_full": [{"header_name": "server", "header_full": "V2R2C00-IAE/1.0", "locality": "local"}],
        "body_match": [
            {"body_match": "http://119.73.65.87:8080/redirect.html?accessurl=", "locality": "isp"},
            {
                "body_match": "As per your subscription of Nayatel Safeweb service, the website you are trying to access is blocked for your viewing",
                "locality": "isp",
            },
        ],
        "dns_full": [
            {"dns_full": "203.82.48.83", "locality": "isp"},
            {"dns_full": "203.82.48.86", "locality": "isp"},
        ],
    },
    "PL": {
        "header_full": [
            {
                "header_full": "http://www.finanse.mf.gov.pl/inne-podatki/podatek-od-gier-gry-hazardowe/komunikat",
                "header_name": "location",
                "locality": "country",
            },
            {
                "header_full": "https://www.finanse.mf.gov.pl/inne-podatki/podatek-od-gier-gry-hazardowe/komunikat",
                "header_name": "location",
                "locality": "country",
            },
        ],
        "dns_full": [
            {"dns_full": "145.237.235.240", "locality": "country"},
            {"dns_full": "195.187.6.33", "locality": "country"},
            {"dns_full": "195.187.6.34", "locality": "country"},
            {"dns_full": "195.187.6.35", "locality": "country"},
            {"dns_full": "78.133.250.166", "locality": "country"},
            {"dns_full": "195.116.107.98", "locality": "country"},
        ],
        "header_prefix": [
            {
                "header_prefix": "http://80.50.144.142/UserCheck/PortalMain",
                "header_name": "location",
                "locality": "isp",
            }
        ],
    },
    "PT": {
        "body_match": [
            {"body_match": "<title>Bloqueado por ordem judicial</title>", "locality": "isp"},
            {
                "body_match": "<title>Acesso bloqueado por entidade judici&aacute;ria</title>",
                "locality": "isp",
            },
        ],
        "header_full": [
            {
                "header_full": "http://mobilegen.vodafone.pt/denied/dn",
                "header_name": "location",
                "locality": "isp",
            }
        ],
    },
    "QA": {
        "header_full": [
            {"header_full": "http://www.vodafone.qa/alu.cfm", "header_name": "location", "locality": "isp"}
        ],
        "body_match": [
            {"body_match": "censor.qa/?accessurl=", "locality": "isp"},
            {"body_match": "censor.qa/?dpid=", "locality": "isp"},
        ],
    },
    "RO": {
        "body_match": [
            {
                "body_match": "Accesul dumneavoastră către acest site a fost restricționat",
                "locality": "country",
            }
        ]
    },
    "RU": {
        "body_match": [
            {
                "body_match": "Доступ к сайту ограничен в соответствии с Федеральными законами",
                "locality": "country",
            },
            {
                "body_match": "распространение которой в Российской Федерации запрещено! Данный ресурс включен в ЕДИНЫЙ РЕЕСТР доменных имен, указателей страниц сайтов в сети «Интернет» и сетевых адресов, позволяющих идентифицировать",
                "locality": "country",
            },
            {"body_match": '<iframe src="http://subblock.mts.ru/api', "locality": "isp"},
            {"body_match": "<h1>Доступ к запрашиваемому ресурсу закрыт.", "locality": "country"},
            {"body_match": "http://eais.rkn.gov.ru/", "locality": "country"},
            {"body_match": "Орион телеком :: ДОСТУП ЗАПРЕЩЕН", "locality": "isp"},
            {
                "body_match": "Доступ к запрашиваемому Вами Интернет-ресурсу ограничен в <br>",
                "locality": "isp",
            },
            {"body_match": "//t2rkn.com/", "locality": "isp"},
            {"body_match": "TTK :: Доступ к ресурсу ограничен", "locality": "isp"},
            {"body_match": "i.imgur.com/KMKuXmA.png", "locality": "isp"},
            {
                "body_match": "PEhUTUwgc3R5bGU9ImZvbnQtZmFtaWx5OiBHZW5ldmEsIEhlbHZldGljYSwgc2Fucy1zZXJpZjsiPgoKCTxIRUFEPgoJCTxUSVRMRT5BY2Nlc3MgUmVzdHJpY3RlZCE8L1RJVExFPgoJCTwhLS0gPHRpdGxlPuTP09TV0CDPx9LBzsnexc48L3RpdGxlPiAtLT4KCQkgICAgICAKCQk8TUVUQSBIVFRQLUVRVUlWPSJDb250ZW50LVR5cGUiIENPTlRFTlQ9InRleHQvaHRtbDsgY2hhcnNldD1rb2k4LXIiPgoJPC9IRUFEPgoJCgk8Qk9EWT4KCQoJICAgIDxESVYgc3R5bGU9ImhlaWdodDoxMDAlOyB3aWR0aDoxMDAlOyBwb3NpdGlvbjpmaXhlZDsgdG9wOjA7IGxlZnQ6MDsgZGlzcGxheTpmbGV4OyBhbGlnbi1pdGVtczpjZW50ZXI7IGp1c3RpZnktY29udGVudDogY2VudGVyOyBvdmVyZmxvdzphdXRvOyI",
                "locality": "isp",
            },
            {
                "body_match": "PCFET0NUWVBFIGh0bWwgUFVCTElDICItLy9XM0MvL0RURCBYSFRNTCAxLjAgVHJhbnNpdGlvbmFsLy9FTiIgImh0dHA6Ly93d3cudzMub3JnL1RSL3hodG1sMS9EVEQveGh0bWwxLXRyYW5zaXRpb25hbC5kdGQiPgo8IS0tIHNhdmVkIGZyb20gdXJsPSgwMDE1KWh0dHA6Ly96ZXJ4LnJ1LyAtLT4KPGh0bWwgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkveGh0bWwiPjxoZWFkPjxtZXRhIGh0dHAtZXF1aXY9IkNvbnRlbnQtVHlwZSIgY29udGVudD0idGV4dC9odG1sOyBjaGFyc2V0PXdpbmRvd3MtMTI1MSIN",
                "locality": "isp",
            },
            {"body_match": "<title>block-system</title>", "locality": "isp"},
            {"body_match": "<title>Federal block</title>", "locality": "isp"},
            {"body_match": "http://www.beeline.ru/customers/help/safe-beeline/", "locality": "isp"},
            {"body_match": "UA-2468561-43", "locality": "isp"},
            {"body_match": ".akado-ural.ru/web/rkn/site_blocked.css", "locality": "isp"},
            {"body_match": "185.36.60.2/icons/logo.png", "locality": "isp"},
            {"body_match": "МФТИ-Телеком&nbsp;&nbsp;</td>", "locality": "isp"},
            {"body_match": "rkn.ucanet.ru", "locality": "isp"},
            {"body_match": "www.lanta-net.ru/zapret/", "locality": "isp"},
            {"body_match": "almatel.ru/ajax/all.php?e=ott_forbidden_reg", "locality": "isp"},
            {"body_match": "GTM-NBL6CQ", "locality": "isp"},
            {"body_match": "UA-16019436-1", "locality": "isp"},
            {"body_match": "rkn.clkon.net/images/", "locality": "isp"},
            {
                "body_match": "id=com.intersvyaz.lk&referrer=utm_source%3Dlp_you_shall_not_pass_parking",
                "locality": "isp",
            },
            {"body_match": "UA-97554836-1", "locality": "isp"},
            {"body_match": "GTM-WBQ8X7M", "locality": "isp"},
            {"body_match": 'href="rkn">Отменить</a>', "locality": "isp"},
            {"body_match": "id:43845029,", "locality": "isp"},
            {"body_match": "zapret-info.prometey.me", "locality": "isp"},
        ],
        "header_prefix": [
            {"header_name": "location", "header_prefix": "http://erblock.crimea.com/", "locality": "country"},
            {"header_name": "location", "header_prefix": "http://warning.rt.ru", "locality": "country"},
            {"header_name": "location", "header_prefix": "http://block.orionnet.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://site-blocked.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://block.intersat.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://zapret.2090000.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "195.146.65.20/block.html", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "http://stat.profintel.ru/block/blacklist/",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "http://blockpage.kmv.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://blacklist.planeta.tc", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "http://89.185.75.227/451/1f50893f80d6830d62765ffad7721742.html",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "http://blocked.mgts.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "https://block.mgts.ru", "locality": "isp"},
            {
                "exp_url": "https://explorer.ooni.org/measurement/20180826T070129Z_AS25513_Oc2jCi998XSfV1AccJgCanulDVWpm8PBG7tEZeiOF2nuh8FFIj?input=http://www.deti-404.com/",
                "header_name": "location",
                "header_prefix": "http://62.112.121.68",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "http://block.kf.mgts.ru", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "http://rinet.ru/blocked/index.html",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "http://block.naukanet.ru", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "https://zapret-info.tis-dialog.ru",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "http://block.rt.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://t2blocked.com", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://217.169.82.130/", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://fz139.ttk.ru", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "http://kaspnet.ru/sites/default/files/0.html",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "http://195.94.233.66?UrlRedir=", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://zapret.westcall.net/", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://211.ru/149.html", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "http://blocked.as20764.net/blocked.php",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "http://block.ecotelecom.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://blocked.akado.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://rkn.pakt.ru", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "http://www.skynet-kazan.com/_blocked.htm",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "block.ip.center.rt.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://block.k-telecom.org", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://forbidden.podryad.tv", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://blocked.netbynet.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://blocked.ti.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "https://blocked.tinkoff.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://blocked.ugmk-telecom.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://block.yaltanet.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://deny.cifra1.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://erblock.crimea.com", "locality": "isp"},
            {"header_name": "location", "header_prefix": "https://forbidden.yota.ru", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://forbidden.yota.ru", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "https://cacti.telincom.ru/blocked.html",
                "locality": "isp",
            },
            {
                "header_name": "location",
                "header_prefix": "https://you-shall-not-pass.is74.ru",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "http://sv-en.ru/block.php", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://m.megafonpro.ru", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "https://www.ufanet.ru/blocking.html",
                "locality": "isp",
            },
            {"header_name": "location", "header_prefix": "http://unblock.mts.ru", "locality": "isp"},
            {
                "header_name": "location",
                "header_prefix": "https://vk.com/blank.php?rkn=",
                "locality": "country",
            },
            {"header_name": "location", "header_prefix": "http://95.213.254.253", "locality": "isp"},
            {"header_name": "location", "header_prefix": "http://block.runnet.ru", "locality": "local"},
        ],
        "dns_full": [
            {"dns_full": "159.255.26.69", "locality": "general"},
            {"dns_full": "193.58.251.1", "locality": "general"},
            {"dns_full": "193.58.251.11", "locality": "general"},
            {"dns_full": "95.217.66.240", "locality": "general"},
            {"dns_full": "93.158.134.250", "locality": "general"},
            {"dns_full": "217.148.54.171", "locality": "isp"},
            {"dns_full": "185.37.129.10", "locality": "isp"},
            {"dns_full": "46.175.31.250", "locality": "isp"},
            {"dns_full": "46.175.31.250", "locality": "isp"},
            {"dns_full": "83.69.208.124", "locality": "isp"},
            {"dns_full": "212.1.226.59", "locality": "isp"},
            {"dns_full": "37.44.40.254", "locality": "isp"},
            {"dns_full": "87.241.223.133", "locality": "isp"},
            {"dns_full": "5.3.3.17", "locality": "isp"},
            {"dns_full": "62.33.207.196", "locality": "country"},
            {"dns_full": "62.33.207.197", "locality": "country"},
        ],
    },
    "SA": {
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "http://notify.bluecoat.com/notify-Notify",
                "locality": "local",
            },
            {"header_name": "server", "header_prefix": "Protected by WireFilter", "locality": "country"},
        ],
        "body_match": [{"body_match": "://blocking-web-server.isu.net.sa/", "locality": "local"}],
    },
    "SD": {
        "header_full": [
            {"header_full": "http://196.1.211.6:8080/alert/", "header_name": "location", "locality": "isp"}
        ],
        "header_prefix": [
            {
                "header_prefix": "http://196.29.164.27/ntc/ntcblock.html",
                "header_name": "location",
                "locality": "isp",
            }
        ],
        "body_match": [
            {"body_match": "<title>gateprotect Content Filter Message</title>", "locality": "local"},
            {"body_match": "/webadmin/deny/ptra/blocking.html", "locality": "isp"},
        ],
    },
    "SG": {
        "header_full": [
            {
                "header_full": "http://www.starhub.com:80/personal/broadband/value-added-services/safesurf/mda-blocked.html",
                "header_name": "location",
                "locality": "isp",
            }
        ]
    },
    "TH": {
        "body_match": [
            {
                "body_match": "Sorry. Access to this website has been disabled because the Ministry of Digital Economic",
                "locality": "country",
            },
            {
                "body_match": "pPGh0bWwgeG1sbnM6dj0idXJuOnNjaGVtYXMtbWljcm9zb2Z0LWNvbTp2bWwiDQp4bWxuczpvPSJ1cm46c",
                "locality": "country",
            },
            {"body_match": "http://124.40.225.20/?accessurl=", "locality": "isp"},
            {"body_match": "http://103.208.24.21/?accessurl=", "locality": "isp"},
        ],
        "header_prefix": [
            {"header_name": "location", "header_prefix": "http://103.86.50.16", "locality": "country"},
            {"header_name": "location", "header_prefix": "http://103.208.24.21", "locality": "country"},
            {"header_name": "location", "header_prefix": "http://103.208.24.21", "locality": "country"},
            {
                "header_name": "location",
                "header_prefix": "http://prohibit.ais-idc.com",
                "locality": "country",
            },
            {
                "header_name": "location",
                "header_prefix": "http://110.164.252.137/wpwarn/soft_bd/wpcbt_res.php",
                "locality": "isp",
            },
        ],
        "dns_full": [{"dns_full": "125.26.170.3", "locality": "country"}],
    },
    "TR": {
        "body_match": [
            {"body_match": "<title>Telekomünikasyon İletişim Başkanlığı</title>", "locality": "country"},
            {
                "body_match": '<p class="sub-message">Bu <a href="https://www.goknet.com.tr/iletisim.html">link</a>\'e tıklayarak bize ulaşabilir, daha detaylı bilgi alabilirsiniz.</p>',
                "locality": "isp",
            },
            {
                "body_match": 'class="yazi3_1">After technical analysis and legal consideration based on the law nr. 5651, administration measure has been taken for this website',
                "locality": "country",
            },
            {
                "body_match": "To turn this off, you must verify your age - click below to log in to My3",
                "locality": "isp",
            },
            {"body_match": "<title>Güvenli İnternet Uyarı</title>", "locality": "isp"},
        ],
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "http://bilgi.turktelekom.com.tr/guvenli_internet_uyari",
                "locality": "isp",
            }
        ],
        "dns_full": [
            {"dns_full": "195.175.254.2", "locality": "country"},
            {"dns_full": "193.192.98.41", "locality": "isp"},
            {"dns_full": "193.192.98.42", "locality": "isp"},
            {"dns_full": "193.192.98.43", "locality": "isp"},
            {"dns_full": "193.192.98.45", "locality": "isp"},
            {"dns_full": "193.192.98.46", "locality": "isp"},
            {"dns_full": "193.192.98.47", "locality": "isp"},
            {"dns_full": "193.192.98.48", "locality": "isp"},
            {"dns_full": "193.192.98.49", "locality": "isp"},
        ],
    },
    "UA": {
        "body_match": [{"body_match": "Відвідування даного ресурсу заборонено", "locality": "country"}],
        "header_prefix": [
            {"header_prefix": "http://blocked.triolan.com.ua", "header_name": "location", "locality": "isp"}
        ],
    },
    "UG": {
        "body_match": [
            {
                "body_match": "According to UCC regulation, Pornography pages are restricted for browsing.",
                "locality": "isp",
            }
        ]
    },
    "US": {
        "header_full": [
            {
                "header_full": "1.1 MLD-C-Barracuda.mld.org (http_scan_byf/3.5.16)",
                "header_name": "via",
                "locality": "country",
            },
            {
                "header_full": "1.1 forcepoint-wcg.chambersburg.localnet",
                "header_name": "via",
                "locality": "country",
            },
        ],
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "http://filter.esu9.org:8080/webadmin/deny/index.php",
                "locality": "country",
            },
            {
                "header_name": "location",
                "header_prefix": "http://reporter.dublinschools.net/block/restricted.html",
                "locality": "local",
            },
            {
                "header_name": "location",
                "header_prefix": "http://ibossreporter.edutech.org/block/bp.html",
                "locality": "local",
            },
            {
                "header_name": "location",
                "header_prefix": "http://alert.scansafe.net/alert/process",
                "locality": "local",
            },
            {
                "header_name": "location",
                "header_prefix": "http://184.168.221.96:6080/php/urlblock.php",
                "locality": "local",
            },
            {
                "header_name": "location",
                "header_prefix": "https://gateway.wifast.com:443/wifidog/login/",
                "locality": "local",
            },
            {
                "header_name": "location",
                "header_prefix": "https://mpswebfilterwashbu.mpls.k12.mn.us:6082/php/uid.php",
                "locality": "local",
            },
        ],
        "body_match": [
            {"body_match": "<title>Access to this site is blocked</title>", "locality": "local"},
            {
                "body_match": "It is a good idea to check to see if the NetSweeper restriction is coming from the cache of your web browser",
                "locality": "local",
            },
            {
                "body_match": "https://staff.mpls.k12.mn.us/Depts/its/Pages/Block-Unblock-Requests.aspx",
                "locality": "local",
            },
            {"body_match": "Jeffco Schools Internet Filtering Page", "locality": "local"},
        ],
    },
    "VN": {
        "header_prefix": [
            {
                "header_name": "location",
                "header_prefix": "http://ezxcess.antlabs.com/login/index.ant?url",
                "locality": "local",
            }
        ]
    },
    "YE": {
        "body_match": [
            {"body_match": "http://82.114.160.94/webadmin/deny/", "locality": "isp"},
            {"body_match": "http://deny.yemen.net.ye/webadmin/deny", "locality": "isp"},
        ]
    },
    "UZ": {
        "header_prefix": [
            {"header_name": "location", "header_prefix": "http://reestr.mitc.uz/", "locality": "country"}
        ]
    },
}
