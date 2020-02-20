import csv

# TODO
# Below are measurements for failing transparent http proxies:
# https://explorer.ooni.org/measurement/20170509T041918Z_AS5384_fSeP50M6LS3lUhIarj2WhbQNIQS8mKtvhuxEhwJOhgheEL7EsZ?input=http:%2F%2Fanonym.to
# https://explorer.ooni.org/measurement/20180914T010619Z_AS11427_d3lligD9zAEneBLYeI8Mt2JUpVBC2y5zFZ1EG3XNLo1smBQa48?input=http:%2F%2Fmoqavemat.ir
# though they don't not look like a blockpage

# TODO(explorer error)
# https://explorer.ooni.org/measurement/20170722T013346Z_AS14340_QXOwhyfxJUPRGWsCqanoOycTnbHcpU4CW3NBNXUMMbxbi3Q6I3?input=http:%2F%2Fwww.blubster.com
#https://explorer.ooni.org/measurement/20181118T123404Z_AS7922_pgeD0Ka5ySsyl55RBYXO07V82WoH0uggCYFJsvlcp2d55Tju3i?input=http:%2F%2Fwww.acdi-cida.gc.ca

# blocking locality: global > country > isp > local
# unclassified locality is named "general"
fingerprints = {
    "AE": [
        {
            "header_name": "Server",
            "header_prefix": "Protected by WireFilter",
            "locality": "country",
        },
        # https://github.com/ooni/pipeline/issues/163
        # https://explorer.ooni.org/measurement/20170423T142350Z_AS0_5EG4lO5Z8KHN2jwbqB5hQqxlC44iXq2A2YCxoASGvY5Z05KrGL?input=http:%2F%2Fwww.foxnews.com
        {
            "header_name": "Location",
            "header_prefix": "http://www.bluecoat.com/notify-NotifyUser1",
            "locality": "country"
        }
    ],
    "AF": [
        # https://github.com/ooni/pipeline/issues/155#issue-437678102
        # https://explorer.ooni.org/measurement/20171130T100203Z_AS38742_DmzL8KtUBadHNFU6wchlAgOy7MBwpDH75ZWdNzs0e55ArgFffx?input=http:%2F%2Fhowtogrowmarijuana.com
        {
            "body_match": "content=\"Access Denied - Afghan Wireless Communication Company",
            "locality": "isp",
        }
    ],
    "AR": [
        # https://github.com/ooni/pipeline/issues/178
        # https://explorer.ooni.org/measurement/20170312T225529Z_AS0_hV7ESTIV4phKrhXxhO9NTxc5XrcXsgzPqZzEkYbrSjgPv9Xyor?input=http:%2F%2Fwww.erogeschichten.com
        {
            "body_match": "<title>Notificación: política: filtrado de URL</title>",
            #"header_full": "1.1 FC-WSA-FibertelZone3.int.fibercorp.com.ar:80 (Cisco-WSA/10.1.0-204)",
            #"header_name": "Via",
            "locality": "isp",
        }
    ],
    "AU": [
        # https://github.com/ooni/pipeline/issues/179
        # https://explorer.ooni.org/measurement/20171106T070150Z_AS9426_z1R8gTMEhKzX69ZVymQrubL1f5FliuHXuFy6Z7TRomXpC5w1jr?input=http:%2F%2Fwww.rollitup.org
        {
            "body_match": "<title>Notification: Policy: URL Filtering</title>",
            #"header_full": "1.1 ac2106-wsag2.wsmartwifi.com.au:80 (Cisco-WSA/10.1.1-235)",
            #"header_name": "Via",
            "locality": "local",
        },
        # https://explorer.ooni.org/measurement/20171119T095401Z_AS1221_sSYzvupLp9kaEiQiBBS4nlqpHzsO59Eh5SIyp60Z83ah5uRXtM?input=http:%2F%2Fwww.twistedinternet.com
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
        # https://github.com/ooni/pipeline/issues/168
        # https://explorer.ooni.org/measurement/20171106T080745Z_AS5432_m0LkLhXH3oxwworJZUpHGmPeJV2Abk3TMxr2dz8wu04ziIUAGA?input=http:%2F%2Fguardster.com%2F
        {
            "header_full": "1.1 webfilter.stjohns.net (http_scan_byf/3.5.16)",
            "header_name": "Via",
            "locality": "local",
        },
    ],
    "BR": [
        # https://github.com/ooni/pipeline/issues/180
        # https://explorer.ooni.org/measurement/20171206T160707Z_AS10429_4pfvLyNqYHpbLQI9tIpuQr7CPgvOOGaZbbnm7gMIZKdBE4oXJ9?input=http:%2F%2Fcrackspider.net
        {
            "header_full": "1.1 wsa07.grupoamil.com.br:80 (Cisco-WSA/9.1.2-010)",
            "header_name": "Via",
            "locality": "local",
        },
        # https://explorer.ooni.org/measurement/20181023T171547Z_AS262318_cr2e8wzvNXORo80y7pOT9iqxLDOaHAboXakfU8qnQkWh50K0cs?input=http:%2F%2Fwww.pandora.com
        {
            "header_full": "SonicWALL",
            "header_name": "Server",
            "locality": "local",
        }
    ],
    "CA": [
        # https://explorer.ooni.org/measurement/20171026T125929Z_AS0_nkYRKqxCJy1PZQ9yBcsFuG61hFzZRYeio3N21CEBwot7MiikfZ?input=http:%2F%2Fwww.schwarzreport.org
        # https://explorer.ooni.org/measurement/20181010T185819Z_AS5664_EeT6QJ84dSl7QaHu9Dwb5TcByIY2qiGrdtcyZlSFotmQlc53Hg?input=http:%2F%2Fwww.sportingbet.com
        # https://explorer.ooni.org/measurement/20170604T114135Z_AS852_pZtNoyGV6fO5K97OJwwhM3ShmlWnuxKHLGrWbjSi4omt9KvyIi?input=http:%2F%2Fwww.xroxy.com
        {
            "body_match": " <title>Notification: Policy: URL Filtering</title>",
            "locality": "local"
        }
    ],
    "CH": [
        # https://github.com/ooni/pipeline/issues/191
        # https://explorer.ooni.org/measurement/43xnHPgN3gi0kt6EhmF2VbIOfQSV5CN9TXicU0A5ChlYejSGjT24Y1noM2DJgdk8?input=http:%2F%2Fwww.wetplace.com
        {
            "header_name": "Location",
            "header_prefix": "https://192.168.88.1/sgerror.php",
            "locality": "local",
        }
    ],
    "CL": [
        # https://github.com/ooni/pipeline/issues/196
        # https://explorer.ooni.org/measurement/20170413T224353Z_AS0_Izup11aUZt39zCD1TSFUC1uvOmg7tO1bhwRHWEYsk2WgNrgObZ?input=http:%2F%2Fshareaza.com%2F
        {
            "header_full": "Kerio Control Embedded Web Server",
            "header_name": "Server",
            "locality": "local",
        }
    ],
    "CO": [
        # https://github.com/ooni/pipeline/issues/156
        # https://explorer.ooni.org/measurement/20190114T112310Z_AS262928_N3ChIPo5QSMMZ3qgA25G9QHE55suubZbPPkAfmNLkmOXuh9ZXJ?input=http:%2F%2Fwww.eurogrand.com%2F
        {
            "body_match": "Esta página ha sido bloqueada por disposición del Ministerio de las TIC,",
            "locality": "country"
        }
    ],
    "CY": [
        {
            "body_match": "nba.com.cy/Eas/eas.nsf/All/6F7F17A7790A55C8C2257B130055C86F",
            "locality": "country",
        }
    ],
    "DE": [
        # https://github.com/ooni/pipeline/issues/181
        # https://explorer.ooni.org/measurement/20180312T143953Z_AS3320_Kumlzdy0NSKyLoB0bt9PHKXp4OKItFMuYqMCw4ouQJapQFVUNR?input=http:%2F%2Fwww.hackhull.com
        # https://explorer.ooni.org/measurement/20170506T130315Z_AS47610_cpNzdaQAx60UxJxEdXh54qBxxEKLexnoPdNam8KDJ181yCbZir?input=http:%2F%2Fspys.ru
        {
            "body_match": "<title>Notification: Policy: URL Filtering</title>",
            #"header_full": "1.1 s690-10.noc.rwth-aachen.de:80 (Cisco-WSA/10.1.1-230)",
            #"header_name": "Via",
            "locality": "local",
        },
        # https://explorer.ooni.org/measurement/20190113T190405Z_AS60068_P7XDllvakD4djyFssTl9xVyVJI5bxSVl6mCxsGFsPLd94ohP8U?input=http:%2F%2Foccupystreams.org
        {
            "header_full": "https://blocked.netalerts.io",
            "header_name": "X-App-Url",
            "locality": "isp",
        },
    ],
    "DK": [
        {"body_match": "lagt at blokere for adgang til siden.", "locality": "country"},
        # https://github.com/ooni/pipeline/issues/182
        # https://explorer.ooni.org/measurement/20171121T193103Z_AS41746_lcM0SY6VKKQ9SnL3SUrh6aiH2hgJUkCs1zGtWuEjYTgVHqW7Lz?input=http:%2F%2Fwww.wetplace.com
        {
            #"header_full": "1.1 dsbpx001.dsb.dk:25 (Cisco-WSA/9.1.1-074)",
            #"header_name": "Via",
            "body_match": "<title>Notification: Policy: URL Filtering</title>",
            "locality": "local",
        },
    ],
    "EG": [
        # https://github.com/ooni/pipeline/issues/193
        # https://explorer.ooni.org/measurement/20171126T053414Z_AS36992_8F2afEp0cM9V7Who1mEJUpqX2fGVbvgoZ2DfVGi3Nv3lQzypzV?input=http:%2F%2Fkh-press.com
        {
            "header_name": "Location",
            "header_prefix": "http://notification.etisalat.com.eg/etisalat/notification/redirectionactions.html?",
            "locality": "isp",
        }
    ],
    "ES": [
        # https://github.com/ooni/pipeline/issues/82#issue-260659726
        # https://explorer.ooni.org/measurement/20170925T151843Z_AS12338_JMQ1OWOJQQ4WsPmSNRi6HsR5w5tMSX2IgNeXhLN5wUCB7051jX?input=http:%2F%2Fwww.ref1oct.eu%2F
        {
            "body_match": "<title>Dominio-No-Disponible</title>",
            "locality": "global",
        },
        # https://explorer.ooni.org/measurement/20180523T140922Z_AS12430_ZRebsyxxswrlcQhz1wEs6apHw5Br7FWNc1LenCsVR6Rkl1OCSD?input=http:%2F%2Fwww.marijuana.com
        {
            "header_name": "Server",
            "header_full": "V2R2C00-IAE/1.0",
            "locality": "local",
        },
    ],
    "FR": [
        {"body_match": 'xtpage = "page-blocage-terrorisme"', "locality": "country"},
        # https://github.com/ooni/pipeline/issues/184
        # https://explorer.ooni.org/measurement/20170213T143932Z_AS57584_U1gMCvIFLNWIKnSrpWTLrN9oewaHiT0DdKjLaT3MiMqnBk3J3U?input=http:%2F%2Fwww.23.org
        {
            #"header_full": "1.1 proxy2.rmc.local:80 (Cisco-WSA/9.1.1-074)",
            #"header_name": "Via",
            "body_match": "<title>Notification: Policy: URL Filtering</title>",
            "locality": "local",
        },
    ],
    "GB": [
        # https://github.com/ooni/pipeline/issues/188
        # https://explorer.ooni.org/measurement/20160401T061018Z_ehdZlDMzbUsYhYSGSWalmqKnqGIynfVHQhKvocrcKEmFeynXHd?input=Trans500.com
        {
            "header_name": "Location",
            "header_prefix": "http://blocked.nb.sky.com",
            "locality": "isp",
        },
        # https://explorer.ooni.org/measurement/20181118T215552Z_AS12576_LXCqBnsH90yHeMcE6LNDYwOl6IHnop0dTroWxA5NE7AhJ8vFn9?input=http:%2F%2Fwww.globalfire.tv
        {
            "header_full": "http://ee.co.uk/help/my-account/corporate-content-lock",
            "header_name": "Location",
            "locality": "isp",
        },
        # https://explorer.ooni.org/measurement/20181120T092944Z_AS199335_6V7Di7t3qUP7qVBYDlOHo9nxgle5NMQIDGHV50wtmCLuZTVPzU?input=http:%2F%2Fwww.microsofttranslator.com
        {
            "header_name": "Location",
            "header_prefix": "http://Filter7external.schoolsbroadband.co.uk/access",
            "locality": "isp",
        },
        # http://localhost:3100/measurement/20170605T124503Z_AS0_eVo3z6wXAYDVrAZDsgqiM7pPlLuKR7l4zNF8oEUrGmZ62HWU4l?input=http:%2F%2Frockettube.com
        {
            "header_name": "Location",
            "header_prefix": "https://account.nowtv.com/broadband-buddy/blocked-pages/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180127T090022Z_AS5378_NK5M8lt6WbL1LOdiIooPX5PXla2DQDlAkGIK4HimIWbUpoMlj8?input=http:%2F%2Fwww.imageshack.us
        {
            "header_full": "www.vodafone.co.uk/contentcontrolpage/vfb-category-blocklist.html",
            "header_name": "Location",
            "locality": "isp",
        },
        # https://explorer.ooni.org/measurement/20190203T142614Z_AS60339_PIMtdDSw9QEc2C9hDgA8tx5LZDrdmUP8ZFsSkdGRX2QNnisqaM?input=http:%2F%2Fwww.peacefire.org%2Fcircumventor%2Fsimple-circumventor-instructions.html
        {
            "header_full": "http://three.co.uk/mobilebroadband_restricted",
            "header_name": "Location",
            "locality": "isp",
        },
        # https://explorer.ooni.org/measurement/20170404T062436Z_AS60339_QJa9jOkZrduHeY2fH5oQmChKFtqwM1RzB3RG2AAjE1IMDMXp59?input=http:%2F%2Fwww.naughty.com
        {
            "body_match": '<a href="https://smobile.three.co.uk/837/">Age Validation</a>',
            "locality": "isp"
        }
    ],
    "GF": [{"body_match": 'xtpage = "page-blocage-terrorisme"', "locality": "country"}],
    "GR": [
        {
            "body_match": "www.gamingcommission.gov.gr/index.php/forbidden-access-black-list/",
            "locality": "country",
        },
        # https://github.com/ooni/pipeline/issues/187
        # https://explorer.ooni.org/measurement/20140703T083044Z_xCnGLSGTjBtyHfCTRvswNcQAjkhIwkpDWJrXqyTCjeMVCECmnv?input=http:%2F%2Fwww.royalvegascasino.com%2F
        {
            "header_prefix": "http://1.2.3.50/ups/no_access",
            "header_name": "Location",
            "locality": "isp",
        }
    ],
    "HU": [
        # https://github.com/ooni/pipeline/issues/223
        # https://explorer.ooni.org/measurement/20190905T104808Z_AS50261_Y03a7meiLbuSNLjxa55pvOAYug9r0yjsFjlmfe64MzbDuGJ2UM?input=http://www.realbeer.com/
        {
            "body_match": "<title>Oops! Website blocked!</title>",
            "locality": "local"
        },
        # https://explorer.ooni.org/measurement/20190904T091911Z_AS1955_V5wcmlVrMPVZzi9sQcgAiopUjZr8umfv8XY3zHY8rOQvbTssHU?input=http://guardster.com/
        {
            "body_match": "<title>Web Page Blocked</title>",
            "locality": "local"
        }
    ],
    "ID": [
        {
            "header_name": "Location",
            "header_prefix": "http://internet-positif.org",
            "locality": "country",
        },
        # https://explorer.ooni.org/measurement/20170826T071505Z_AS24526_40Tlz7tR7m0UVaTRZi5EUtsuAjHnYuAgDlNjkec64t70Tujbo9?input=http:%2F%2Fwww.budweiser.com
        {
            "body_match": '<title>Blocked Page Bina Nusantara Networks</title>',
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
    "IT": [
        {
            "body_match": "GdF Stop Page",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20170216T161517Z_AS203469_NhQfyO3SkGoX5gdyzo1VRQTrZv1HcQgzudlItMI4YxuSUfgLib?input=http:%2F%2Fwww.pokerstars.net
        {
            "header_name": "Server",
            "header_full": "V2R2C00-IAE/1.0",
            "locality": "local",
        },
        # The following is not necessarily a blockpage
        # https://explorer.ooni.org/measurement/3N5bdjWAdVjZubaIyAxCCAg0HiZYWfT1YLgz6cI0zRq1XTjHzBmGg49AbRxOGILi?input=http:%2F%2Fwarc.jalb.de
        {
            "header_full": "WebProxy/1.0 Pre-Alpha",
            "header_name": "Server",
            "locality": "local",
        }
    ],
    # https://github.com/ooni/pipeline/issues/192
    # https://explorer.ooni.org/measurement/20180611T174527Z_AS33771_xGoXddliTIGLP3NJUBkEnEL1ukvMZKs7YvbB7RNFb3tW4OKZR7?input=http:%2F%2Fprotectionline.org%2F
    #"KE": [
    #    {
    #        "header_name": "Location",
    #        "header_prefix": "http://159.89.232.4/alert",
    #        "locality": "country",
    #    }
    #],
    "KR": [
        # https://github.com/ooni/pipeline/issues/131
        # https://explorer.ooni.org/measurement/20181204T023538Z_AS4766_Q7tnDXKYbZxJAArIYzQwgd4y91BDuYsPZvA0MrYvUZzEVX6Olz?input=http:%2F%2Fwww.torproject.org
        {
            "body_match": "cm/cheongshim/img/cheongshim_block.png",
            "locality": "local"
        },
        {
            "body_match": "http://warning.or.kr",
            "locality": "country"
        },
        {
            "header_full": "http://www.warning.or.kr",
            "header_name": "Location",
            "locality": "country",
        },
    ],
    "KG": [
        # https://github.com/ooni/pipeline/issues/122
        # https://explorer.ooni.org/measurement/20180126T000430Z_AS8449_pk15Mr2LgOhNOk9NfI2EarhUAM64DZ3R85nh4Z3q2m56hflUGh?input=http:%2F%2Farchive.org
        {
            "header_name": "Location",
            "header_full": "http://homeline.kg/access/blockpage.html",
            "locality": "isp"
        }
    ],
    "KW": [
        # https://github.com/ooni/pipeline/issues/174
        # https://explorer.ooni.org/measurement/20170804T144746Z_AS42961_nClauBGJlQ5BgV1lAVD72Gw8omqphSogfCSLAc55zTAdlcpzTA?input=http:%2F%2Fwww.radioislam.org
        {
            "header_name": "Location",
            "header_prefix": "http://restrict.kw.zain.com",
            "locality": "isp"
        }
    ],
    "MX": [
        # https://github.com/ooni/pipeline/issues/159
        # https://explorer.ooni.org/measurement/20190306T161639Z_AS22908_1iCBIVT3AGu4mDvEtpl0ECfxp1oSw8UYXSg82JFQ1gOIqOvw8y?input=http:%2F%2Fwww.pornhub.com%2F
        {
            "header_name": "Server",
            "header_full": "V2R2C00-IAE/1.0",
            "locality": "local",
        }
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
        # https://github.com/ooni/pipeline/issues/170
        # https://explorer.ooni.org/measurement/20170302T184253Z_AS11556_LrU69C7D1dqVTi05dMN0jPphf601DuAzMnFBrehfFvR4ccwfoe?input=http:%2F%2Flifestream.aol.com
        {
            "body_match": "<p>Redirecting you to Barracuda Web Filter.</p>",
            "locality": "local",
        }
    ],
    "PH": [
        # https://explorer.ooni.org/measurement/20180114T101054Z_AS0_SptN5g552QQ9wpfhEBsOTeuOkrpYOQgCBc4JQXNy9GFGxarbEf?input=http:%2F%2Fhightimes.com
        {
            "header_name": "Location",
            "header_prefix": "http://surfalert.globe.com.ph/usedpromo?dest_url",
            "locality": "isp",
        },
        # TODO this is actually a captive portal like scenario
        # https://explorer.ooni.org/measurement/20171014T140144Z_AS10139_gQG3LIHnMZH3IsSJuPmMlLM8qDj3kKfHxJJGyPblDQ1AOFFyBX?input=http:%2F%2Fwww.bittorrent.com
        {
            "header_full": "http://cube.sunbroadband.ph:8020/balanceToOffer/init",
            "header_name": "Location",
            "locality": "isp",
        },
    ],
    "PK": [
        # https://github.com/ooni/pipeline/issues/160
        # https://explorer.ooni.org/measurement/20180721T184612Z_AS45773_w5kQp1GbCQUbIv3VDzezjxNx1nCt3IaW7WpvrZTNvayksz9FBK?input=http:%2F%2Fwww.xbox.com
        {
            "header_name": "Server",
            "header_full": "V2R2C00-IAE/1.0",
            "locality": "local",
        },
    ],
    "PL": [
        # https://github.com/ooni/pipeline/issues/224
        # https://explorer.ooni.org/measurement/20190911T110527Z_AS6830_kkm1ZGUCJI4dSrRV4xl6QwG77o7EeI2PDKbwt9SPL9BBJHUsTr?input=http://www.eurogrand.com/
        {
            "header_full": "http://www.finanse.mf.gov.pl/inne-podatki/podatek-od-gier-gry-hazardowe/komunikat",
            "header_name": "Location",
            "locality": "country"
        },
        {
            "header_prefix": "http://80.50.144.142/UserCheck/PortalMain",
            "header_name": "Location",
            "locality": "isp"
        }
    ],
    "PT": [
        # https://github.com/ooni/pipeline/issues/225
        # https://explorer.ooni.org/measurement/20190911T103335Z_AS2860_4aKH0micNlcrjnWcRknF9ghAykfMdxMkWGhXWracX2FIBY6UQb?input=http://www.roxypalace.com/
        {
            "body_match": "<title>Bloqueado por ordem judicial</title>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180910T235247Z_AS3243_LpUldhcfbVGUIyfOxF6TFfLNT1wSAMwHy54LBz6owWe0cofJIK?input=http://www.luckynugget.com
        {
            "body_match": "<title>Acesso bloqueado por entidade judici&aacute;ria</title>",
            "locality": "isp"
        },
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
        # https://github.com/ooni/pipeline/issues/115
        # https://explorer.ooni.org/measurement/20180315T230339Z_AS15378_1OT3ZGTyarLfiET0jYHJZigX2B1oQDdJKdrjkfzq5Zqr30Lvlp?input=http:%2F%2Fqha.com.ua%2F
        {
            "body_match": "распространение которой в Российской Федерации запрещено! Данный ресурс включен в ЕДИНЫЙ РЕЕСТР доменных имен, указателей страниц сайтов в сети «Интернет» и сетевых адресов, позволяющих идентифицировать",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20180315T100250Z_AS6789_KYIQLsidOroJuPSP8DNkM8WFYOwNEAKebucOYOHhr9bwel8Yl3?input=http:%2F%2Fqha.com.ua%2F
        {
            "header_name": "Location",
            "header_prefix": "http://erblock.crimea.com/",
            "locality": "country",
        },
        # https://explorer.ooni.org/measurement/20180315T160455Z_AS8359_t1zebVigtFmS7kxCOCe3P77uClvciZHmKIwutI13x3Wcpe5t9V?input=http:%2F%2Futronews.org
        {
            "body_match": "<iframe src=\"http://subblock.mts.ru/api",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180315T174422Z_AS12688_7Iy8vwd6JYREOl2E6E1PJnNeCVGVKlORQNYhUJ2tKyiWjaEFkY?input=http:%2F%2Fmaidanua.org%2F
        # {"dns_match": "62.33.207.196", "locality": "country"},
        # {"dns_match": "62.33.207.197", "locality": "country"},
        # https://explorer.ooni.org/measurement/20181229T072204Z_AS39289_xlYTdPez910QvwBFCYyD3sgv0hQq1WBgbhW3lMjIs3MVMUdGtg?input=http:%2F%2Fblackberry.com
        {
            # Using the Location header is a possible alternative
            # "header_prefix": "http://89.185.75.227/451/",
            # "header_name": "Location",
            "body_match": "<h1>Доступ к запрашиваемому ресурсу закрыт.",
            "locality": "country"
        },
        {
            "body_match": "http://eais.rkn.gov.ru/",
            "locality": "country"
        },
        {
            "header_name": "Location",
            "header_prefix": "http://warning.rt.ru",
            "locality": "country",
        },
    ],
    "SA": [
        # TODO maybe we would to classify this as knowing the vendor
        # https://github.com/ooni/pipeline/issues/164
        # https://explorer.ooni.org/measurement/20180717T084426Z_AS15505_0NtuQmtvJpAZG5I4V8QtVrS5PeUnqplLxvm3zDflzPm7ywFmX0?input=http:%2F%2Fwww.163.com
        {
            "header_name": "Location",
            "header_prefix": "http://notify.bluecoat.com/notify-Notify",
            "locality": "local"
        },
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
            "locality": "isp",
        },
        # https://explorer.ooni.org/measurement/20181221T173618Z_AS33788_NH383fTiPbg28uZGbH9Huk4jEPJZ00IBUNrqZWLoEpbl9sx3VQ?input=http:%2F%2Fwww.pokerstars.com
        {
            "header_prefix": "http://196.29.164.27/ntc/ntcblock.html",
            "header_name": "Location",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20181223T053338Z_AS37211_SNSyW5GQvxWDuQ2tQpJNZKqK5IyQFfXAVgTQynYjVzUvZn2FDK?input=http:%2F%2Fwww.bglad.com
        {
            "body_match": "<title>gateprotect Content Filter Message</title>",
            "locality": "local"
        }
    ],
    "SG": [
        # https://github.com/ooni/pipeline/issues/195
        # https://explorer.ooni.org/measurement/20170905T231542Z_AS9874_3TJ6zyJeL17MVkTArLLsVfDxuMEPzfWB2rm4UbxiDuwtSiuNf3?input=http:%2F%2Fwww.playboy.com
        {
            "header_full": "http://www.starhub.com:80/personal/broadband/value-added-services/safesurf/mda-blocked.html",
            "header_name": "Location",
            "locality": "isp",
        }
    ],
    "TR": [
        {
            "body_match": "<title>Telekom\u00fcnikasyon \u0130leti\u015fim Ba\u015fkanl\u0131\u011f\u0131</title>",
            "locality": "country",
        },
        # https://github.com/ooni/pipeline/issues/161
        # https://explorer.ooni.org/measurement/20170210T045710Z_AS201411_Xu0QrPJeKuNvYdTpTs3Uv9u4usmdcNACeLPi3wtiqxzBtpOLMf?input=http:%2F%2Fwww.365gay.com
        {
            "body_match": "<p class=\"sub-message\">Bu <a href=\"https://www.goknet.com.tr/iletisim.html\">link</a>'e tıklayarak bize ulaşabilir, daha detaylı bilgi alabilirsiniz.</p>",
            "locality": "isp",
        },
        # https://github.com/ooni/pipeline/issues/117
        # https://explorer.ooni.org/measurement/20180403T183403Z_AS9121_FfHjDmPkC0E5UoU3JMZoXJ2KRrMVyqdeTkHchmGEqAonEU64u4?input=http:%2F%2Fbeeg.com
        {
            "body_match": "class=\"yazi3_1\">After technical analysis and legal consideration based on the law nr. 5651, administration measure has been taken for this website",
            "locality": "country"
        }
        # https://explorer.ooni.org/measurement/20180403T183403Z_AS9121_FfHjDmPkC0E5UoU3JMZoXJ2KRrMVyqdeTkHchmGEqAonEU64u4?input=http:%2F%2Fbeeg.com
        # {"dns_match": "195.175.254.2", "locality": "country"},
    ],
    "UA": [
        # https://github.com/ooni/pipeline/issues/121
        # https://explorer.ooni.org/measurement/20180615T125414Z_AS35362_GaNRQSk6HlZ1Aa2ZD9UoGiIgu3KcLMM5M5yk5dEswhEkIprbnA?input=http:%2F%2Fvk.com%2Fminitrue
        {
            "body_match": "Відвідування даного ресурсу заборонено",
            "locality": "country",
        },
        # https://explorer.ooni.org/measurement/20190228T101440Z_AS13188_LUWIsztkSQlApx6cliGdGzztCM6Hs2MFI3ybFEYuaIG5W8cQS6?input=http:%2F%2Freporter-crimea.ru
        {
            "header_prefix": "http://blocked.triolan.com.ua",
            "header_name": "Location",
            "locality": "isp"
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
        # https://explorer.ooni.org/measurement/20170411T170124Z_AS46491_ntYaNL2kdnuHFhOpkSgje3aadGsvRW8oadtjIC71DuiX06z4yy?input=http:%2F%2Fwww.exgay.com
        {
            "header_name": "Location",
            "header_prefix": "http://reporter.dublinschools.net/block/restricted.html",
            "locality": "local",
        },
        # https://explorer.ooni.org/measurement/20170504T143706Z_AS16657_2LnvAcQgpCrjBG46Fb5EKr50PIL40W0ppwNcXp9WCCatbPboXK?input=http:%2F%2Fchinadaily.com.cn
        # https://explorer.ooni.org/measurement/20170915T220312Z_AS22935_6FKfune3ZuFavfORPXNul209Ffwv3jL7RyjzMJppxYju2caAoE?input=http:%2F%2Fwww.breastenlargementmagazine.com
        {
            "header_name": "Location",
            "header_prefix": "http://ibossreporter.edutech.org/block/bp.html",
            "locality": "local",
        },
        # https://explorer.ooni.org/measurement/20170628T182856Z_AS25605_Lev8VClbbZplNkYfBGujzPiKFI7rHxERx9SNwOfuR1M8WCTBSZ?input=http:%2F%2Fwww.aceshigh.com
        {
            "header_name": "Location",
            "header_prefix": "http://alert.scansafe.net/alert/process",
            "locality": "local",
        },
        # https://explorer.ooni.io/measurement/20170722T013346Z_AS14340_QXOwhyfxJUPRGWsCqanoOycTnbHcpU4CW3NBNXUMMbxbi3Q6I3?input=http:%2F%2Fwww.blubster.com
        {
            "header_name": "Location",
            "header_prefix": "http://184.168.221.96:6080/php/urlblock.php",
            "locality": "local",
        },
        {
            "header_name": "Location",
            "header_prefix": "https://gateway.wifast.com:443/wifidog/login/",
            "locality": "local",
        },
        # https://explorer.ooni.org/measurement/20190205T191943Z_AS26638_QbFGhgqZ8sqXmCQrZNrNgB0RWB6EUfjFYPbKYOgaihiWLv5xNb?input=http:%2F%2Ftwitter.com%2F
        {
            "header_name": "Location",
            "header_prefix": "https://mpswebfilterwashbu.mpls.k12.mn.us:6082/php/uid.php",
            "locality": "local",
        },
        # https://explorer.ooni.org/measurement/20180406T152727Z_AS39942_lquPnt0vjeXydfleOdSkxyjst6VTiUWb58f3x5qlFKTSlTIQLG?input=http:%2F%2Fflirtylingerie.com%2F
        # vendor: forcepoint
        {
            "body_match": "<title>Access to this site is blocked</title>",
            "locality": "local"
        },
        # https://explorer.ooni.org/measurement/20171129T155619Z_AS11714_vJUMktHjy0cQGKqYqY3fgOQQLVNfnxb1V11fvP6jTXTbbTX60e?input=http:%2F%2Fwww.pandora.com
        # vendor: netsweeper
        {
            "body_match": "It is a good idea to check to see if the NetSweeper restriction is coming from the cache of your web browser",
            "locality": "local"
        },
    ],
    "VN": [
        # https://github.com/ooni/pipeline/issues/186
        # https://explorer.ooni.org/measurement/20130506T043500Z_IBzthJbAAPsdFZQLPrjMbAwlELzGqtabqMatKpBqqBSWnUyQnA?input=http:%2F%2Fwww.sos-reporters.net
        {
            "header_name": "Location",
            "header_prefix": "http://ezxcess.antlabs.com/login/index.ant?url",
            "locality": "local",
        }
    ],
    "ZZ": [
        {
            "header_name": "Location",
            "header_prefix": "http://1.2.3.50/ups/no_access",
            "locality": "isp",
        },
        # https://github.com/ooni/pipeline/issues/179
        # https://explorer.ooni.org/measurement/20180125T012951Z_AS0_gyX2DUR5Q1W5V7gAlvUwnnEAH5tbEkEexlUu5qO8ZphH2uEjk6?input=http:%2F%2F8thstreetlatinas.com
        {
            "header_name": "Location",
            "header_prefix": "http://www.webscanningservice.com/WebServicesAlertPage/WebURLAlert.aspx",
            "locality": "isp",
        },
        # https://github.com/ooni/pipeline/issues/169
        # https://explorer.ooni.org/measurement/20180724T151542Z_AS577_YiqZVd01jKCgmtm4Ixf6z2uzSBcFSsXkeN6NIDjHl1dtWZ6VrX?input=http:%2F%2Fwww.genderandaids.org
        # https://github.com/ooni/pipeline/issues/171
        # https://explorer.ooni.org/measurement/20171029T080350Z_AS209_xtJYWXrUShSnXnvStZUPWsVpqVhT0hOzR749tbJgzxF9OkR1Bn?input=http:%2F%2Fwww.vanguardnewsnetwork.com
        # https://explorer.ooni.org/measurement/20170814T120242Z_AS8447_g6CoCriPHXMWjXJHwZ9kjJmTusVWVPYEsOKOOhF1HLwrHR29hp?input=http:%2F%2Fwww.aleph.to
        # https://explorer.ooni.org/measurement/20180215T142531Z_AS31543_HutYcy6eALgop44KgGsXAsaF2i7v4feM6DP5vb2hST8nZdmWta?input=http:%2F%2Fanonymizer.secuser.com
        {
            "header_name": "Server",
            "header_full": "Barracuda/NGFirewall",
            "locality": "local"
        },
        # https://explorer.ooni.org/measurement/20180123T210247Z_AS7385_VLsJ9z4UYNZIMUK3Nc4cyaXctKPnnIsxIhuU97X4XWvSAubgZs?input=http:%2F%2Fwww.figleaves.com
        # https://explorer.ooni.org/measurement/20171203T130750Z_AS14434_iviy15O0b7YXVRoTMaqS4O0w1w9NfVaOL4l3KoV4Y9mJEq33X0?input=http:%2F%2Fcompany.wizards.com%2F
        {
            "header_name": "Server",
            "header_full": "BarracudaHTTP 4.0",
            "locality": "local"
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
