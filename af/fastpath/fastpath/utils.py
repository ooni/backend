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
        # https://explorer.ooni.org/measurement/20200119T122050Z_AS5384_c3w6BLgePoeH9DLcYiH5MbgwfNujXtBUPNkMzpHmn1tdxZdn4P?input=http://www.helem.net/
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
        },
        # https://explorer.ooni.org/measurement/20191118T063541Z_AS15802_ocKS0RbSg8GE1oLahQKYeAozvsxM3HglG8f3xMRkrWVOd4ajtN?input=http://gayguide.net/
        # https://explorer.ooni.org/measurement/20171105T032733Z_AS15802_HaY0S8nTvD8xcK50zBOzcdDFCLiqhjVRFAFhPnUowVNv582Tp6?input=http://amygoodloe.com/lesbian-dot-org/
        # https://explorer.ooni.org/measurement/20200127T092537Z_AS15802_GvFE8kAEn7C40Sq0vlu5OUmUxAP89DajF7LRzqs51Bl8eztjip?input=http://www.gayscape.com/
        # https://explorer.ooni.org/measurement/20171105T032733Z_AS15802_HaY0S8nTvD8xcK50zBOzcdDFCLiqhjVRFAFhPnUowVNv582Tp6?input=http://amygoodloe.com/lesbian-dot-org/
        {
            "header_name": "Location",
            "header_prefix": "http://lighthouse.du.ae",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190708T075453Z_AS5384_VXPZQorUMS5VJxSy4BWbzITW3GGfQOWX9APTD9wBEJDCCDU4s5?input=http://gaytoday.com/
        {
            "body_match": "it-security-operations@etisalat.ae",
            "locality": "isp"
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
        # https://explorer.ooni.org/measurement/20190727T072541Z_AS132909_MpSZSKk7KLUGwYzXlP6Q1BTllFuPXmFxAZjvUyZrOYjJa6RlVD?input=http://gaytoday.com/
        {
            "body_match": "Blocked by ContentKeeper",
            "locality": "isp"
        }
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
    "BH": [
        # https://explorer.ooni.org/measurement/20200103T214930Z_AS5416_Cb0eigi9DgBdD9lrQfZLTSckVYANzKDOzI5LSd9yPbFcJNEUuT?input=http://www.gay.com/
        {
            "body_match": "www.anonymous.com.bh",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180821T225240Z_AS51375_arIbEdkOsq47wsCE8tRpJWQuIeDN8adphRYo1e76drI3rZWRWr?input=http://gaytoday.com
        {
            "body_match": "www.viva.com.bh/static/block",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20170220T113603Z_AS39015_Lamk4jT9RlMfeIjwMbg4oi8xBU67dBgnWwzD7Nb4UhihIaR0Ap?input=http://gaytoday.com
        {
            "body_match": "menatelecom.com/deny_page.html",
            "locality": "isp"
        }
    ],
    "BY": [
        # https://explorer.ooni.org/measurement/20200809T064736Z_AS42772_Sn8W1QKfDMxmJzphNHpEWpYmWbyNQS09eB8wgpQQCYIASBbkPh?input=http://intimby.net/
        {
            "header_name": "Location",
            "header_prefix": "https://www.a1.by/mininfo/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200808T143914Z_AS6697_vIveEEZm32Xz4qc8nChMRmJQvQXS2vKLEFQ553NmpborhsfzDY?input=http://intimby.net/
        {
            "header_name": "Location",
            "header_prefix": "http://82.209.230.23",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200808T195507Z_AS25106_hY9xbufjqUKiqPI5LZJ4IqiwfGMNcaOdrtKnwCaXADPRhSOL8J?input=http://intimby.net/
        {
            "header_name": "Location",
            "header_prefix": "https://internet.mts.by/blocked/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200809T060553Z_AS6697_WHViLvwEDfLrt3yRqACQW09MnDhCy6jynycEEfObNuAApaBTpv?input=https://vk.com/pramenofanarchy
        {
            "header_name": "Location",
            "header_prefix": "https://vk.com/blank.php?rkn=",
            "locality": "country"
        },
        {"dns_full": "134.17.0.7", "locality": "isp"}
    ],
    "CA": [
        # https://explorer.ooni.org/measurement/20171026T125929Z_AS0_nkYRKqxCJy1PZQ9yBcsFuG61hFzZRYeio3N21CEBwot7MiikfZ?input=http:%2F%2Fwww.schwarzreport.org
        # https://explorer.ooni.org/measurement/20181010T185819Z_AS5664_EeT6QJ84dSl7QaHu9Dwb5TcByIY2qiGrdtcyZlSFotmQlc53Hg?input=http:%2F%2Fwww.sportingbet.com
        # https://explorer.ooni.org/measurement/20170604T114135Z_AS852_pZtNoyGV6fO5K97OJwwhM3ShmlWnuxKHLGrWbjSi4omt9KvyIi?input=http:%2F%2Fwww.xroxy.com
        {
            "body_match": " <title>Notification: Policy: URL Filtering</title>",
            "locality": "local"
        },
        {
            "body_match": "Access to this site has been blocked by an Order issued by the Federal Court of Canada",
            "locality": "isp"
        },
        {
            "body_match": "Access to the location you have attempted to reach has been disabled pursuant to an Order&nbsp;of the Federal Court (Canada)",
            "locality": "isp"
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
    "CN": [
        {"dns_full": "8.7.198.45", "locality": "country"},
        {"dns_full": "37.61.54.158", "locality": "country"},
        {"dns_full": "46.82.174.68", "locality": "country"},
        # https://explorer.ooni.org/measurement/20191205T074509Z_AS4134_snD532tevf4HneyRwKvtRLSxBppvIFgxGq8FwjFKH3R1eSVv1m?input=http://kareemazmy.blogspot.com/
        {"dns_full": "78.16.49.15", "locality": "country"},
        {"dns_full": "93.46.8.89", "locality": "country"},
        {"dns_full": "159.106.121.75", "locality": "country"},
        {"dns_full": "203.98.7.65", "locality": "country"},
        {"dns_full": "59.24.3.173", "locality": "country"},
        {"dns_full": "203.98.7.65", "locality": "country"},
        {"dns_full": "243.185.187.39", "locality": "country"}
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
        # https://explorer.ooni.org/measurement/20191129T093025Z_AS31334_QLJPBWGVj5ZqNmPb7C3R4KQkEatrbGCQu9nVQQwgkNH4SnWxpZ?input=http://www.newnownext.com/
        {
            "body_match": "title>IServ",
            "locality": "local"
        },
        # https://explorer.ooni.org/measurement/20200127T113040Z_AS31334_f2WzvfEf8rj0X645IsaTmrojbWpB4VpU48c7TRifHnwrEPT1J7?input=http://www.nclrights.org/
        {
            "header_name": "Location",
            "header_prefix": "https://hotspot.vodafone.de/access_denied.html",
            "locality": "isp"
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
        {
            "body_match": 'xtpage = "page-blocage-terrorisme"',
            "locality": "country"
        },
        # https://github.com/ooni/pipeline/issues/184
        # https://explorer.ooni.org/measurement/20170213T143932Z_AS57584_U1gMCvIFLNWIKnSrpWTLrN9oewaHiT0DdKjLaT3MiMqnBk3J3U?input=http:%2F%2Fwww.23.org
        {
            #"header_full": "1.1 proxy2.rmc.local:80 (Cisco-WSA/9.1.1-074)",
            #"header_name": "Via",
            "body_match": "<title>Notification: Policy: URL Filtering</title>",
            "locality": "local",
        },
        # https://explorer.ooni.org/measurement/20181013T160011Z_AS3215_IRIYlWDvBY8FTKrWmI3C6GrvGXVEeHwibS9J9AeorEPZbKp62j?input=http://gaytoday.com
        {
            "header_name": "Server",
            "header_prefix": "Olfeo",
            "locality": "local"
        }
    ],
    "GB": [
        # https://explorer.ooni.org/measurement/20190403T143637Z_AS29180_Rg2EoxvcDr0pcIYCywybM010BYCl8skvqZk7yAQbArxo2lHSJJ?input=http://www.bglad.com/
        {
            "header_name": "Location",
            "header_prefix": "http://assets.o2.co.uk/18plusaccess/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190704T000814Z_AS25135_mqMcWW8a9uRprR4q1bWdrsOnWMgJnQljybCpd5pJ488dXV3zYw?input=http://www.bglad.com
        {
            "header_name": "Location",
            "header_prefix": "http://www.vodafone.co.uk/restricted-content",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191009T152456Z_AS35228_2YC8q7bdXWrnOO8NuKvNjS5F0SsVQBHLCyt17C5i684qDQ7DQT?input=http://www.bglad.com/
        {
            "header_name": "Location",
            "header_prefix": "https://www.giffgaff.com/mobile/over18",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190929T145217Z_AS5607_2kkJ5ZcoHY65PnXshBrnVW1SkwHUGBJYgKApmQ82qYQl5U6kkC?input=http://www.grindr.com/
        {
            "header_name": "Location",
            "header_prefix": "http://block.cf.sky.com",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190523T171133Z_AS12513_H6Wc12khwbndgeJ9oKath0nvUZ4IeEcmNSCxmcTpYPe59MdSpV?input=http://www.grindr.com/
        {
            "body_match": "Taunton School allow access to the following search engines",
            "locality": "local"
        },
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
        # https://explorer.ooni.org/measurement/20180528T130640Z_AS7713_A2RVHOGPmVoYQ5U9Fe3WNCMkJcH7D2kCmPboBZDEfgt6XjE8OM?input=http://www.samesexmarriage.ca
        {
            "header_name": "Location",
            "header_prefix": "http://internetpositif.uzone.id",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20200312T024737Z_AS45292_QGO96hC1JiPt1T30OH3q4EXyCDfE8D3c4cjGqalbffrgJCrbe9?input=http://ilga.org/
        {
            "header_name": "Location",
            "header_prefix": "http://mercusuar.uzone.id/",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20200213T053902Z_AS17974_igK3SmCYSdqnVjV2OxZ1VCUnsaECgo8Dh7S6CfU0AQgWg5nPQU?input=http://www.queernet.org/
        {
            "body_match": "http://block.uzone.id",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20170414T032645Z_AS17974_Qho7Y39z1oG2s1ylGbQvoFuQh8aDDnY2OwhXMVkqmyBPwQjmT5?input=http://www.bglad.com
        {
            "body_match": ".uzone.id/assets/internetpositif",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20171121T103829Z_AS17974_QgZkCjksBNucHe11XDLxKXIC3MTW32OamXngJCJrLaoouWNoEM?input=http://www.ifge.org
        {
            "body_match": "positif.uzone.id",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20190314T214950Z_AS17658_kybYxwcXIxWZYnX32z36B1ZprSLxFT3WpxY0g7sfuy0Uy7MLAo?input=http://www.samesexmarriage.ca/
        {
            "body_match": "This page is blocked by <a href=http://trustpositif.kominfo.go.id",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20170214T023529Z_AS17974_1hVbJGBPLdOsxQvNgIawwvABxfZuLNeVK5VaY1XWajguEt0yK3?input=http://www.lesbian.org
        {
            "body_match": "tidak bisa diakses melalui jaringan ini sesuai peraturan perundang-undangan",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20180727T095622Z_AS17670_ryQ3v3ZDI2X8YI7FKTxeG9L5PEmgc0Z5N3bDIU7uusFaaIcuql?input=http://www.bglad.com
        {
            "body_match": "internetpositif.mncplaymedia.com",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190420T092536Z_AS135478_mLOlXUu4n0QwTV10X6nqZYFwh9aQga4i4fPo9fMomwk2IMV6Le?input=http://transsexual.org/
        {
            "body_match": "Maaf, akses Anda ke situs ini telah diblokir sesuai dengan <a",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20170213T013637Z_AS4832_Y8ct5af944VzPhrMoeoll3Ap7MtHL97R2JBO0lEHto45vPYwFQ?input=http://www.gayscape.com
        {
            "body_match": "We are blocking this abusive site as stated by the Indonesia regulation in order to provide Internet Sehat.",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20161031T235715Z_AS23700_3cxMXOKGRHBMQly8HBD4vFHM3qRsMKtzc5Yl8Dcm8LVeQasRLj?input=http://www.bglad.com
        {
            "body_match": "internetsehatdanamanfastnet.html",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191124T035958Z_AS23700_qdrRmnIMyFi0rfhj3OnrSb94TDyu7uRcw9vRTM1mjghyJGnAJW?input=http://ilga.org/
        {
            "body_match": "var pname='internet-sehat';",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190301T020519Z_AS55666_zcD5kLAL3QHZypge7Kppqp2ysd5p76afVPmvC7XlZ8zol52iEl?input=http://ilga.org/
        {
            "body_match": "xblock.gmedia.net.id",
            "locality": "isp"
        },
        {
            "body_match": "http://crypto.net.id/images/crypto_emblem.png",
            "locality": "isp"
        },
        {
            "body_match": "<title>Negatif Konten</title>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190323T072437Z_AS0_pvl7biYGsLZDaHODVWbZ1PHC3iijtVfwM4a7BmBOd3YCg8705w?input=http://www.tsroadmap.com
        {
            "body_match": "<a href=http://megavision.net.id>StarNet Project</a></strong> - DNS Filter Project.",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20170920T165858Z_AS17974_3WOOOvd6aU5LlWGoP1mVIXMiXBDXaJpAwfkjP4IYR52V0nXvDF?input=http://transsexual.org
        {
            "header_name": "Location",
            "header_prefix": "http://filter.citra.net.id",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20171010T001639Z_AS17974_DRF1cmT5lEsJdMlrkJ6xtFk4FW4zwAJHmf0eYBmCzoNFFHSgua?input=http://www.bglad.com
        {
            "body_match": "<h2>INTERNET SEHAT CITRANET</h2>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200213T135057Z_AS4761_0VqghBlufZfB6k68FBcGkeU9XAUcCmfXguHZJGBJhaQfurl2do?input=http://www.grindr.com/
        {
            "body_match": "<title>Indosatooredoo Netsafe</title>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20170403T000118Z_AS4795_ZGyxgVEVzoRMZpL4QlHyPZtmJOwAO26NUv1Op3Vh6fCv7XIAW3?input=http://www.ifge.org
        {
            "body_match": "<title>Netsafe IndosatM2</title>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200213T135057Z_AS4761_0VqghBlufZfB6k68FBcGkeU9XAUcCmfXguHZJGBJhaQfurl2do?input=http://www.grindr.com/
        # https://explorer.ooni.org/measurement/20190602T174828Z_AS4761_YOEBG2rWEL90gfaLLyKNI3kBNU5RjG5ryZ5b3LPd81ayu8oW31?input=http://www.gayegypt.com/
        {
            "body_match": "http://netsafe.indosatooredoo.com",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20170501T123218Z_AS17974_TQovh9GvtBR3FlRa5IfIH19tSRfiGUgUzEnGoh5sgdLI1m0OgY?input=http://www.ifge.org
        {
            "body_match": "argon_files/stop.jpg",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190905T165736Z_AS63859_PeIPMNtOMVuCacZ3pJmR3RySVKbNArcUTaKTPPLgPddZXwN2KC?input=http://www.queernet.org/
        {
            "body_match": "https://myrepublic.co.id/internet-sehat/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200130T135811Z_AS23693_d5uipVzMCxrQlnNCO4cB3ZxZYk4CyYZWr8ipsdgC8Qzp4K2Bl9?input=http://www.bglad.com/
        {
            "body_match": "internetbaik.telkomsel.com/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20170316T024318Z_AS23693_CQPxlyILeqGXlHzFqGSCPR6MgtCBfZtbs3h2l37MOyiU77N1xP?input=http://www.bglad.com
        {
            "body_match": "telkomsel|internet sehat|baik|internet baik",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190307T051144Z_AS131472_7RLBdzGBIF3RPC6UcuV9HJAMkysGP4IR9JkfwfhCSXuieZQtAq?input=http://www.tsroadmap.com
        {
            "body_match": "www.xl.co.id/xlblockpage",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20170412T174345Z_AS24203_qlNBUtI6cL4DZGjeNWLOQ5puycMYiMol71agNH5Qvg1WmSAWzL?input=http://www.bglad.com
        {
            "body_match": "blockpage.xl.co.id",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190727T045744Z_AS17451_kC7sYnleU6DzAOhrgOf4LXXvtois6M4GnEpgvFCcFP0taBcuIU?input=http://www.gayhealth.com/
        {
            "body_match": "www.biznetnetworks.com/safesurf/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190905T052510Z_AS24207_I540tCMJL3Wtb3cJ4oOCQaH7Fv44n2rn8kLkMubuSLLipSctue?input=http://www.gayegypt.com/
        {
            "body_match": "VELO Networks :: Internet Sehat dan Aman",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191005T031241Z_AS45727_93jXiGYrI1w8wHNC9FVzF5zuylmtgOToSGsA0mgYubk132ZKuV?input=http://www.nclrights.org/
        {
            "body_match": "restricted.tri.co.id/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190605T140849Z_AS4800_bKVUk4pjoLXBQOUdWBLnQOPZfWfDPGCSoURwopRoEj0O4ZjOKG?input=http://www.tsroadmap.com/
        {
            "body_match": "<title>IdOLA Lintasarta</title>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180315T084438Z_AS133357_LeDGv9wMP20hFNfN2nqsvJxL1vUKOFZ0grMlnMJXACYHkmPLNB?input=http://www.ifge.org
        {
            "body_match": "<title>Internet Sehat Telkom University</title>",
            "locality": "local"
        },
        # https://explorer.ooni.org/measurement/20190905T165736Z_AS63859_PeIPMNtOMVuCacZ3pJmR3RySVKbNArcUTaKTPPLgPddZXwN2KC?input=http://www.queernet.org/
        {
            "header_name": "Location",
            "header_prefix": "http://block.myrepublic.co.id",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200130T135811Z_AS23693_d5uipVzMCxrQlnNCO4cB3ZxZYk4CyYZWr8ipsdgC8Qzp4K2Bl9?input=http://www.bglad.com/
        {
            "header_name": "Location",
            "header_prefix": "https://internetbaik.telkomsel.com/block?",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180308T104910Z_AS24203_nhfe7SS0mYB7NFo906daTIuBIz5qPAue9LDvWSAw7p2E3hjUna?input=http://www.tsroadmap.com
        {
            "header_name": "Location",
            "header_prefix": "https://blockpage.xl.co.id",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191005T031241Z_AS45727_93jXiGYrI1w8wHNC9FVzF5zuylmtgOToSGsA0mgYubk132ZKuV?input=http://www.nclrights.org/
        {
            "header_name": "Location",
            "header_prefix": "http://restricted.tri.co.id",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20170826T071505Z_AS24526_40Tlz7tR7m0UVaTRZi5EUtsuAjHnYuAgDlNjkec64t70Tujbo9?input=http:%2F%2Fwww.budweiser.com
        {
            "body_match": '<title>Blocked Page Bina Nusantara Networks</title>',
            "locality": "isp",
        },
        # https://explorer.ooni.org/measurement/20200130T121354Z_AS18103_6roxhkcpVP4ML3VyjL75G28deYvsJgocbDyeV8Ud6WBHAFTwy4?input=http://www.grindr.com/
        {
            "body_match": "di.og.ofnimok@netnoknauda",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20170214T023529Z_AS17974_1hVbJGBPLdOsxQvNgIawwvABxfZuLNeVK5VaY1XWajguEt0yK3?input=http://www.lesbian.org
        {"dns_full": "180.131.146.7", "locality": "general"},
        # https://explorer.ooni.org/measurement/20170316T024318Z_AS23693_CQPxlyILeqGXlHzFqGSCPR6MgtCBfZtbs3h2l37MOyiU77N1xP?input=http://www.bglad.com
        {"dns_full": "202.3.219.209", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20200329T090119Z_AS45727_GqQe4DZduLsSaYZB6qnqeMpsNgJn7dTvEaoEFZ0eGGmjyBoQG4?input=https://www.scruff.com/
        {"dns_full": "restricted.tri.co.id", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20200329T090119Z_AS45727_GqQe4DZduLsSaYZB6qnqeMpsNgJn7dTvEaoEFZ0eGGmjyBoQG4?input=https://www.scruff.com/
        {"dns_full": "116.206.10.31", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20171025T095349Z_AS131709_vvCnDreaVjMN1MQ2imNyl4ynBG4EhIZRdWHJIBKgOexJSnaWcb?input=http://www.bglad.com
        {"dns_full": "36.86.63.185", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20191114T004142Z_AS17974_zSo1qO4rG5Isd8Rr2WGTHYV4hwK9jeGkR201ACNu7np3CxXqOQ?input=http://ilga.org/
        {"dns_full": "internet-positif.org", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20191114T004142Z_AS17974_zSo1qO4rG5Isd8Rr2WGTHYV4hwK9jeGkR201ACNu7np3CxXqOQ?input=http://ilga.org/
        {"dns_full": "mypage.blocked.bltsel", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20191114T004142Z_AS17974_zSo1qO4rG5Isd8Rr2WGTHYV4hwK9jeGkR201ACNu7np3CxXqOQ?input=http://ilga.org/
        {"dns_full": "114.121.254.4", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20170307T194134Z_AS45727_gEN976jgNQgOx6CuLiiYDb2flPY8CpNtRPcnrHTwjggcats4At?input=http://www.gay.com
        {"dns_full": "180.214.232.61", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20170213T013637Z_AS4832_Y8ct5af944VzPhrMoeoll3Ap7MtHL97R2JBO0lEHto45vPYwFQ?input=http://www.gayscape.com
        {"dns_full": "202.62.29.1", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20170916T151028Z_AS63859_OMzXkgk31oMZMCyxyswHDc9s7PcHYUDMAm8BEsKSmcioamnK0f?input=http://www.gayscape.com
        {"dns_full": "103.47.132.195", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20190420T092536Z_AS135478_mLOlXUu4n0QwTV10X6nqZYFwh9aQga4i4fPo9fMomwk2IMV6Le?input=http://transsexual.org/
        {"dns_full": "internetsehataman.cbn.net.id", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20180324T031959Z_AS24203_oRMW0HPO6Z2u3lkA8d4uROtqX2fuKU6XH8ARB0JtGanxPSHX3L?input=https://www.scruff.com/
        {"dns_full": "blockpage.xl.co.id", "locality": "isp"},
        #
        {"dns_full": "202.52.141.98", "locality": "isp"},
        #
        {"dns_full": "150.107.140.200", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20181006T114052Z_AS9657_yU1pa9b0I0vRzcBU5OsWOV6phrI2FBxQosem0mJRQdKZupCPkE?input=http://bisexual.org/
        {"dns_full": "103.14.16.18", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20170620T000111Z_AS0_5is0TiDSWSWQSmW01Yc1B4kQFQsMmPhLT2vKSqFsVhuYzbPYvd?input=http://www.gayscape.com
        {"dns_full": "113.197.108.236", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20170920T165858Z_AS17974_3WOOOvd6aU5LlWGoP1mVIXMiXBDXaJpAwfkjP4IYR52V0nXvDF?input=http://www.advocate.com
        {"dns_full": "202.65.113.54", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20170501T123218Z_AS17974_TQovh9GvtBR3FlRa5IfIH19tSRfiGUgUzEnGoh5sgdLI1m0OgY?input=http://www.ifge.org
        {"dns_full": "103.195.19.54", "locality": "isp"},
        {"dns_full": "103.10.120.3", "locality": "isp"},
        {"dns_full": "27.123.220.197", "locality": "isp"},
        {"dns_full": "103.108.159.238", "locality": "isp"},
        {"dns_full": "103.126.10.252", "locality": "isp"},
        {"dns_full": "103.142.60.250", "locality": "isp"},
        {"dns_full": "103.19.56.2", "locality": "isp"},
        {"dns_full": "103.70.68.68", "locality": "isp"},
        {"dns_full": "103.83.96.242", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20170323T040824Z_AS38758_zjtAoJrqVgnQCOYSHGqrVt4bSHxEUGnj0DvgJqHEJMKnnmllir?input=http://transsexual.org
        {"dns_full": "114.129.22.33", "locality": "isp"},
        {"dns_full": "114.129.23.9", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20170330T110102Z_AS4795_yod1sqqu9NwrIBlJDfMepLmyAp3zVxQK5QG6Qqux11QuioLrYJ?input=https://www.gay.com/
        {"dns_full": "netsafe.indosatm2.com", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20170608T035018Z_AS4761_HEJ2bT3U6QBEL4IdHLTPpWshehej9EcxiwssgeMxRTlBLQeLJx?input=http://www.glil.org
        {"dns_full": "114.6.128.8", "locality": "isp"},
        {"dns_full": "150.107.151.151", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20180601T040605Z_AS63859_uzo47992c80YC59mVTgn649d8nTkGPtm3Z8TZ69jdWAmMMMkCb?input=http://www.samesexmarriage.ca
        {"dns_full": "158.140.186.3", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20190612T150505Z_AS23700_e7qsqPDY72QkdwPcDeUb5NkHxZ9HgpHOuU8p5oNFp5uW4BJAk7?input=https://www.shoe.org/
        {"dns_full": "internetpositif3.firstmedia.com", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20181006T114052Z_AS9657_yU1pa9b0I0vRzcBU5OsWOV6phrI2FBxQosem0mJRQdKZupCPkE?input=http://www.bglad.com
        {"dns_full": "filter.melsa.net.id", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20190314T214950Z_AS17658_kybYxwcXIxWZYnX32z36B1ZprSLxFT3WpxY0g7sfuy0Uy7MLAo?input=https://www.ilga-europe.org/
        {"dns_full": "block.centrin.net.id", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20190605T140849Z_AS4800_bKVUk4pjoLXBQOUdWBLnQOPZfWfDPGCSoURwopRoEj0O4ZjOKG?input=http://www.tsroadmap.com/
        {"dns_full": "202.152.4.67", "locality": "isp"},
        {"dns_full": "202.165.36.253", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20171105T072208Z_AS17451_7r3LG7AAcL538QaLjG44o23fmyWhbFiEOWEnbZfDhu1Lfpg6jF?input=http://www.grindr.com/
        {"dns_full": "202.169.44.80", "locality": "isp"},
        #
        {"dns_full": "202.50.202.50", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20190924T072134Z_AS17995_Seinciq0527hnzfIuN4ZQvKYqy8NKBKGHK9vt01KkY79iofutj?input=http://www.gayhealth.com/
        {"dns_full": "trustpositif.iforte.net.id", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20180119T081053Z_AS45287_NWeT8zKRcKd7z2WYMntHuw2GIwqK0zCAh0A5UnvxzKw4s9rN0u?input=http://www.gayhealth.com
        {"dns_full": "202.56.160.131", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20180119T081053Z_AS45287_NWeT8zKRcKd7z2WYMntHuw2GIwqK0zCAh0A5UnvxzKw4s9rN0u?input=http://www.gayhealth.com
        {"dns_full": "202.56.160.132", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20180224T051609Z_AS45287_IoqMH28cD0RwJsIYHmj0rMDUt8oigefrA7YweS4lZ0ahxrDrDy?input=http://www.gay.com/
        {"dns_full": "203.99.130.131", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20171120T160605Z_AS0_J83hVqCVk4VUk9IGei68s4rSrT0F9OWHa3EzXwz6iJaHcxCO6J?input=https://www.gay.com/
        {"dns_full": "203.119.13.75", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20200130T121354Z_AS18103_6roxhkcpVP4ML3VyjL75G28deYvsJgocbDyeV8Ud6WBHAFTwy4?input=http://www.bglad.com/
        {"dns_full": "203.119.13.76", "locality": "isp"},
        {"dns_full": "203.160.56.38", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20200213T075343Z_AS131111_n3Zv50ZiRaGIm7uCn3IwOIN879EzYbr3OV08aHpZdOIzsk83iT?input=https://www.ilga-europe.org/
        {"dns_full": "220.247.168.195", "locality": "isp"},
        {"dns_full": "58.147.184.141", "locality": "isp"},
        {"dns_full": "58.147.185.131", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20161003T063421Z_AS23700_BcAJiWTdgtzSTE5ezaPJoywgMdwm8hZm8yb6Hw3iUB8atIiJCI?input=http://transsexual.org
        {"dns_full": "202.73.99.3", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20190301T020519Z_AS55666_zcD5kLAL3QHZypge7Kppqp2ysd5p76afVPmvC7XlZ8zol52iEl?input=http://ilga.org/
        {"dns_full": "xblock.gmedia.net.id", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20180119T133726Z_AS55666_NfgRumGXxCBp0t0SjoNsX0KyrzzmQmoXbSoXzPfHgw9ICwI5zr?input=http://www.queernet.org
        {"dns_full": "49.128.177.13", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20191225T231001Z_AS18004_hA8xsVHcbUOLZLKxI8kAQ2GV3yzQ8TpDNqUpHA1Sm3Mdb3yYVB?input=http://www.samesexmarriage.ca/
        {"dns_full": "internetsehat.smartfren.com", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20180727T095622Z_AS17670_ryQ3v3ZDI2X8YI7FKTxeG9L5PEmgc0Z5N3bDIU7uusFaaIcuql?input=http://www.bglad.com
        {"dns_full": "internetpositif.mncplaymedia.com", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20180315T084438Z_AS133357_LeDGv9wMP20hFNfN2nqsvJxL1vUKOFZ0grMlnMJXACYHkmPLNB?input=http://transsexual.org
        {"dns_full": "dnssehat.telkomuniversity.ac.id", "locality": "isp"},
        {"dns_full": "trustpositif.kominfo.go.id", "locality": "country"}
    ],
    "IE": [
        # https://explorer.ooni.org/measurement/20190724T152019Z_AS13280_5XchAx4T8ZNmgtqbFSgcjHFB9QKFqviPSJa88PQs4VXCdk1mBo?input=http://www.gayscape.com/
        {
            "header_name": "Location",
            "header_prefix": "https://m.three.ie/adult-content",
            "locality": "isp"
        },
    ],
    "IL": [
        # https://explorer.ooni.org/measurement/20190820T203403Z_AS199391_BKc62QxMlSz5esuRV2hHpMsUArF7fTeaeRAc8eN0Eb2uE4NVtV?input=http://www.ifge.org/
        {
            "body_match": "http://mobile.netsparkmobile.com/?a=block",
            "locality": "isp"
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
        # https://explorer.ooni.org/measurement/20170704T113906Z_AS24560_wfOnnh9CsrttSEJuRH2QRnOhMxICg8j1yVQRMkMd6V54d3qCgS?input=http://www.gayegypt.com
        {
            "body_match": "http://www.airtel.in/dot/?dpid=",
            "locality": "isp"
        },
    ],
    "IR": [
        {
            "body_match": 'iframe src="http://10.10',
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20180627T180515Z_AS44244_Z8V0i4Cr6PoJHByQQ89uN3meAmQbvdUrBli1NqYU8786BLquMk?input=http://alone-persian-man.blogspot.com
        {
            "body_match": "</title></head><body><iframe src=\"http://[d0:0:0:0:0:0:0:11:80]\" style=\"width: 100%; height: 100%\" scrolling=\"no\" marginwidth=\"0\" marginheight=\"0\" frameborder=\"0\" vspace=\"0\" hspace=\"0\"></iframe></body></html>",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20180820T042050Z_AS61173_FPMTdrQeLtEbtLwBjDarQzBlhKVOLhwMbYXGvn9RRcazAFRzRM?input=http://www.wmmh.blogspot.com
        {
          "body_match": "internet.ir/1-2",
          "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20190409T200524Z_AS58224_rPCEFPueXMqioaKnlJnCxocixIQntBMYRps14Iabf3FYimDuRd?input=http://www.wmmh.blogspot.com/
        {
          "body_match": "peyvandha.ir/1-2",
          "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20170525T030641Z_AS50810_5iVwM98EMQORqXeZtbhiDquo9zifyYSMmE5AWTARCw3XJ1R4is?input=http://pesareghabile.blogspot.com
        {"dns_full": "10.10.34.34", "locality": "country"},
        # https://explorer.ooni.org/measurement/20180114T045727Z_AS61173_bkL7bV97kNEYVREkD0Lg4LnvnnlDtlNlbvA1jbzPlsncPdNlIm?input=http://queerquotes.blogspot.com
        {"dns_full": "10.10.34.35", "locality": "country"},
    ],
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
        # https://explorer.ooni.org/measurement/20181227T081659Z_AS4766_7o3rxATU3P7DL8LCWRZU4t84ZionEuDMZwlOwFv1v1JqjKr57r?input=http://www.utopia-asia.com
        {
            "body_match": "cleanmobile01.nate.com",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20181011T032321Z_AS4766_I8APdOqg57wWTVKRvpZJ0uDaHbzHlcrmD3cpmrKuQrJXFsrcnU?input=http://www.gayegypt.com
        {
            "body_match": "cleanmobile02.nate.com",
            "locality": "isp"
        },
        {
            "body_match": "<title>\uccad\uc18c\ub144 \uc720\ud574\ucc28\ub2e8\uc11c\ube44\uc2a4</title>",
            "locality": "isp"
        },
        {
            "header_name": "Location",
            "header_prefix": "http://cleanweb1.uplus.co.kr/kren",
            "locality": "isp"
        }
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
        },
        # https://explorer.ooni.org/measurement/20180424T055755Z_AS21050_QLeo5RlFyonKjcaYnvSrqnR7RGqxhhWjruATjHvNKO8CkQreyV?input=http://www.gayscape.com
        {
            "body_match": "blocked.fasttelco.net/?dpid=",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190323T153406Z_AS47589_XNLYup0tsRncJtSX00WpeMPXC3VZWJhiCFjx5FWLZzCfNhZHk1?input=http://gaytoday.com/
        {
            "body_match": "http://pay.viva.com.kw/images/access-en.jpg",
            "locality": "isp"
        }
    ],
    "MM": [
        # https://explorer.ooni.org/measurement/20210208T105603Z_webconnectivity_MM_58952_n1_NEm53Iw0ysgcGt9J?input=http://www.facebook.com
        {
            "header_name": "Location",
            "header_prefix": "http://notice.myanmarnet.com",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20210208T105603Z_webconnectivity_MM_58952_n1_NEm53Iw0ysgcGt9J?input=http://www.facebook.com
        {
            "body_match": "<li><a href=\"whatever.html\" class=\"menupics\"><img src=\"legaltext.png\" alt=\"descriptivetext\" /></a></li>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20210208T105603Z_webconnectivity_MM_58952_n1_NEm53Iw0ysgcGt9J?input=http://www.facebook.com
        {"dns_full": "59.153.90.11", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20210201T223944Z_webconnectivity_MM_133385_n1_LlJnFqnaVXNfXygL?input=http://www.hornybank.com/
        {"dns_full": "167.172.4.60", "locality": "country"},
    ],
    "MN": [
        {"dns_full": "218.100.84.78", "locality": "country"},
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
        {
            "body_match": "Makluman/Notification", 
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20190829T162515Z_AS24020_0ezmhWkibgyIWMDFfSZmCMhLKQewB5r6nwsf53v7OqCbAMyKRi?input=http://gaytoday.com/
        {
            "header_name": "Location",
            "header_prefix": "https://wifi.uitm.edu.my",
            "locality": "local"
        },
        # https://explorer.ooni.org/measurement/20160817T033110Z_AS4788_jk5ghw4QwieT2JOFiIqto9Z2LzCFhP05v3U0sCcaetBr50NxuU?input=http:%2F%2Fwww.sarawakreport.org%2Ftag%2F1mdb
        # https://explorer.ooni.org/measurement/20190503T024619Z_AS4788_agTXVdX7lipOjGFLnaQQFSkxEMVNoXopd20czlazmSW5XIofs4?input=http://www.gaystarnews.com/
        {"dns_full": "175.139.142.25", "locality": "country"},
    ],
    "NO": [
        {
            "header_full": "http://block-no.altibox.net/",
            "header_name": "Location",
            "locality": "country",
        },
    ],
    "NP": [
        # https://explorer.ooni.org/measurement/20191118T090209Z_AS17501_cqniUNeXAKeoabJN6Zr7EwpuebIM4f7g2fCAZqN0SfYOuMZMcD?input=http://www.newnownext.com/
        {
            "header_name": "Location",
            "header_prefix": "http://blockdomain.worldlink.com.np",
            "locality": "isp"
        },
         # https://explorer.ooni.org/measurement/20191118T090209Z_AS17501_cqniUNeXAKeoabJN6Zr7EwpuebIM4f7g2fCAZqN0SfYOuMZMcD?input=http://www.newnownext.com/
        {
          "body_match": "nta.gov.np/en/notice-regarding-site-block",
          "locality": "isp"
        }
    ],
    "OM": [
        # https://explorer.ooni.org/measurement/20171008T164257Z_AS28885_x73TSE1uoiU8cTEo0NxxBkjRfV1tHOYoQplxDvNTGzxi9vkKIY?input=http://www.gayscape.com
        {
            "body_match": "block.om/newrequestform.aspx?accessurl=",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20170215T210727Z_AS50010_aOkarIhF1xmYR53lpC4iy45St2E0yB25zVr7rpqi39tNNHgKnL?input=http://www.scruff.com/
        {
            "body_match": "http://siteblocked.om/?accessurl=",
            "locality": "isp"
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
        {
          "body_match": "http://119.73.65.87:8080/redirect.html?accessurl=",
          "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200215T032555Z_AS23674_baOoSlSUE3rUC8Vtezp4K1QuLCGKasBKezHCHAmQvKnsOUDfel?input=http://www.globalgayz.com/
        {
          "body_match": "As per your subscription of Nayatel Safeweb service, the website you are trying to access is blocked for your viewing",
          "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20161025T235721Z_AS23674_Lldjua1VqHuWrRcILrD3wrfRXiOVP5P3e0wHwJV1MACuOzBFwY?input=http://www.queerty.com
        {"dns_full": "203.82.48.83", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20191206T015807Z_AS23674_BbXvUMwowxajbM9Q1pTeOp84pawo9ccTUsltC6B1vhyNHC2kkM?input=http://gaytoday.com/
        {"dns_full": "203.82.48.86", "locality": "isp"},

    ],
    "PL": [
        # https://github.com/ooni/pipeline/issues/224
        # https://explorer.ooni.org/measurement/20190911T110527Z_AS6830_kkm1ZGUCJI4dSrRV4xl6QwG77o7EeI2PDKbwt9SPL9BBJHUsTr?input=http://www.eurogrand.com/
        {
            "header_full": "http://www.finanse.mf.gov.pl/inne-podatki/podatek-od-gier-gry-hazardowe/komunikat",
            "header_name": "Location",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20210409T092428Z_webconnectivity_PL_12912_n1_DoMtAEf0oFS4J7oc?input=http://www.eurogrand.com/
        {
            "header_full": "https://www.finanse.mf.gov.pl/inne-podatki/podatek-od-gier-gry-hazardowe/komunikat",
            "header_name": "Location",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20210814T181316Z_webconnectivity_PL_6830_n1_SYkkWB22SGFxDWci?input=http://www.eurogrand.com/
        {
            "dns_full": "145.237.235.240",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20210814T182231Z_webconnectivity_PL_47223_n1_7oaXBHkOiFTedMoy?input=http://sub3.blocked-site-hole-cert.pl/
        {
            "dns_full": "195.187.6.33",
            "locality": "country"
        },
        {
            "dns_full": "195.187.6.34",
            "locality": "country"
        },
        {
            "dns_full": "195.187.6.35",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20210814T204223Z_webconnectivity_PL_12912_n1_BkDZpOVduWcGOFcD?input=http://sub3.blocked-site-hole-cert.pl/
        {
            "dns_full": "78.133.250.166",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20210814T212740Z_webconnectivity_PL_5617_n1_9eoomhLK9CV2op6b?input=http://sub3.blocked-site-hole-cert.pl/
        {
            "dns_full": "195.116.107.98",
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
        },
        # https://explorer.ooni.org/measurement/20200101T185215Z_AS42298_Si7iYR3b37Ai654IPgzQUSdRE2HnLKbi8ubdiwvzvGQ0mnWDDF?input=http://www.grindr.com/
        {
          "body_match": "censor.qa/?accessurl=",
          "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20170215T050956Z_AS8781_ArhSFkwQmwTTc46EA5E5GVIK0a85TdbngwJJ3B3wRZ9kZVy060?input=http://gayromeo.com
        {
          "body_match": "censor.qa/?dpid=",
          "locality": "isp"
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
        # https://explorer.ooni.org/measurement/20180318T024825Z_AS31257_nfyc81ftqzpC3spdlHGM8z5mUCR3fhbcBZP9dTSkdidlB2eLMS?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://block.orionnet.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T024825Z_AS31257_nfyc81ftqzpC3spdlHGM8z5mUCR3fhbcBZP9dTSkdidlB2eLMS?input=http://bluesystem.ru/
        {
            "body_match": "Орион телеком :: ДОСТУП ЗАПРЕЩЕН",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T022949Z_AS39927_ixezvoybYaEp6uSlk6Ikof2tJYytEeaVyzffuGRioxHuxTJIqw?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://site-blocked.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200109T111809Z_AS38972_nXN971LWjRPgQi8AkN52iZQwOo8SOV3VkLqvkV6NYSnDGVjWkd?input=http://www.deti-404.com/
        {
            "header_name": "Location",
            "header_prefix": "http://block.intersat.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T070543Z_AS31200_V253RHv9hxMZJA1k3MqyQxreUHCZcXPk5ERo5oe8Dof0klN1iV?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://zapret.2090000.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180426T161628Z_AS0_CWEZrmlwar4W96mZVYgWNq3ICGQMGAAb9g3IJeLt1yGoYWcG34?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "195.146.65.20/block.html",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200215T045010Z_AS28890_zMSKnUXeDyc2AIT0zl1JkHBLyx89vDgeFoXvi3I6iRuBA0XV1Y?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://stat.profintel.ru/block/blacklist/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180317T130121Z_AS12494_4BeSmhJhSVlr2II7km6x1bWG3s4UV02F1PI69cbDm85b97kMaS?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://blockpage.kmv.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T080743Z_AS12668_tteAPafZVumB1iKGUlmJj24vMNIuhsyxoTFqFbtkmxOyUjBoUW?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://blacklist.planeta.tc",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200215T065021Z_AS39289_MA6u7UK8b8tD6lDtpsUIEUnjFOcvvQp3QMRStQcJIC4snikqu2?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://89.185.75.227/451/1f50893f80d6830d62765ffad7721742.html",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200204T193749Z_AS25513_9Z7LP2duZHnf1I5bAjLF196Dl6aEzCaBwFXBegie524WzJ4rJj?input=http://www.deti-404.com/
        # https://explorer.ooni.org/measurement/20200206T193832Z_AS48720_SlLIbMHbU6Z7Nb9HY3gISWDS0s9UKgtvS4Ec9dADxjqaPV6hrH?input=http://www.deti-404.com/
        {
            "header_name": "Location",
            "header_prefix": "http://blocked.mgts.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180314T172713Z_AS25513_JKzji9R0aZ8eAUuEplDoPGOZgZS3VxCFlnbFcyfQjTDXefoL7g?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "https://block.mgts.ru",
            "locality": "isp"
        },
        {
            "exp_url": "https://explorer.ooni.org/measurement/20180826T070129Z_AS25513_Oc2jCi998XSfV1AccJgCanulDVWpm8PBG7tEZeiOF2nuh8FFIj?input=http://www.deti-404.com/",
            "header_name": "Location",
            "header_prefix": "http://62.112.121.68",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20171125T060158Z_AS25513_qFQyEl7yxNubN8DjveszHUl8t8mfzEFKV5M1pAqpwOPoBNxxhN?input=http://www.glil.org
        {
            "header_name": "Location",
            "header_prefix": "http://block.kf.mgts.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180314T172713Z_AS25513_JKzji9R0aZ8eAUuEplDoPGOZgZS3VxCFlnbFcyfQjTDXefoL7g?input=http://bluesystem.ru/
        {
            "body_match": "Доступ к запрашиваемому Вами Интернет-ресурсу ограничен в <br>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180317T143113Z_AS8331_FwDwX6bHEgagwbGdtlaTJABMU3WwQXJOAJxLRoyvMIVnD8BPve?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://rinet.ru/blocked/index.html",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200318T090603Z_AS8641_sZfld8WLVRMRZ6Oa6uj23WNddUJ5zFCFLL5JCNBqorFDn1P050?input=http://www.lesbi.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://block.naukanet.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180320T222703Z_AS31214_pCNLYmthnVmG3G3QPYDFkDkxwUmXiA0kgeNB0T285eQHwIkibU?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "https://zapret-info.tis-dialog.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191118T092317Z_AS42610_3HH5n7Bwuo8ibohIsM7mKmlnsO0Tv0l6dAdIp1d4wG7AVFCSPe?input=http://transsexual.org/
        {
            "header_name": "Location",
            "header_prefix": "http://block.rt.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200313T111001Z_AS48190_FwhjrOV0nkpiCZvICVEdvh1N0h6D8j6Xuk2B6OsYoUYhUU597L?input=http://www.lesbi.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://t2blocked.com",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190809T191432Z_AS15378_fmsQw7Pl5AMY5uxejuU0d095iyVXnfki55sFBPtu799zPhfi0R?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://217.169.82.130/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200130T202021Z_AS12958_HjHGx4wo3WtUxuoElLzjhlNMmEucNTEIftGkafEqn6Ypg9UKDl?input=http://bluesystem.info/
        {
            "body_match": "//t2rkn.com/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200215T063712Z_AS8427_cIJNHs6ysaZH1kt9gI7uAVPGmIDcZOn3UTwX2w7wkMj8SFK3VN?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://fz139.ttk.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T055620Z_AS8427_eLCazBA5rz8M241SW9vuD3Be7ikVb32rpLEk5ys3MuZqodzvwb?input=http://bluesystem.ru/
        {
            "body_match": "TTK :: Доступ к ресурсу ограничен",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190803T010043Z_AS42922_pjHbAidMpZuZp2PN2HzXhXCQZyZlhf0A4hkNqOzB7XbXGzkmHF?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://kaspnet.ru/sites/default/files/0.html",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190803T010043Z_AS42922_pjHbAidMpZuZp2PN2HzXhXCQZyZlhf0A4hkNqOzB7XbXGzkmHF?input=http://bluesystem.ru/
        {
            "body_match": "i.imgur.com/KMKuXmA.png",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190304T004458Z_AS8595_fphvlM2yC2x9Enus1eKlVPrN7kIgEPZ9XCa5WI6I2O6JQAAFcm?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://195.94.233.66?UrlRedir=",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191028T010715Z_AS0_LMZN0lqus9a06Ts9jOPsJqLXpRb88J454clYl7OOYeZdd5vQYq?input=http://www.deti-404.com/
        {
            "header_name": "Location",
            "header_prefix": "http://zapret.westcall.net/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190305T005035Z_AS8595_0vVnWfDYWDzSGKMf5K8k0zUt669Cz12fNbyvNCBKMBEsDpyFOY?input=http://bluesystem.ru/
        {
            "body_match": "PEhUTUwgc3R5bGU9ImZvbnQtZmFtaWx5OiBHZW5ldmEsIEhlbHZldGljYSwgc2Fucy1zZXJpZjsiPgoKCTxIRUFEPgoJCTxUSVRMRT5BY2Nlc3MgUmVzdHJpY3RlZCE8L1RJVExFPgoJCTwhLS0gPHRpdGxlPuTP09TV0CDPx9LBzsnexc48L3RpdGxlPiAtLT4KCQkgICAgICAKCQk8TUVUQSBIVFRQLUVRVUlWPSJDb250ZW50LVR5cGUiIENPTlRFTlQ9InRleHQvaHRtbDsgY2hhcnNldD1rb2k4LXIiPgoJPC9IRUFEPgoJCgk8Qk9EWT4KCQoJICAgIDxESVYgc3R5bGU9ImhlaWdodDoxMDAlOyB3aWR0aDoxMDAlOyBwb3NpdGlvbjpmaXhlZDsgdG9wOjA7IGxlZnQ6MDsgZGlzcGxheTpmbGV4OyBhbGlnbi1pdGVtczpjZW50ZXI7IGp1c3RpZnktY29udGVudDogY2VudGVyOyBvdmVyZmxvdzphdXRvOyI",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T101233Z_AS34757_dIAMaflYtvY3WlkTT0q8l0iDnP0tzztQeacqAYTniCXQDG2G7F?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://211.ru/149.html",
            "locality": "isp"
        },
        {
            "body_match": "PCFET0NUWVBFIGh0bWwgUFVCTElDICItLy9XM0MvL0RURCBYSFRNTCAxLjAgVHJhbnNpdGlvbmFsLy9FTiIgImh0dHA6Ly93d3cudzMub3JnL1RSL3hodG1sMS9EVEQveGh0bWwxLXRyYW5zaXRpb25hbC5kdGQiPgo8IS0tIHNhdmVkIGZyb20gdXJsPSgwMDE1KWh0dHA6Ly96ZXJ4LnJ1LyAtLT4KPGh0bWwgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkveGh0bWwiPjxoZWFkPjxtZXRhIGh0dHAtZXF1aXY9IkNvbnRlbnQtVHlwZSIgY29udGVudD0idGV4dC9odG1sOyBjaGFyc2V0PXdpbmRvd3MtMTI1MSIN",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T052642Z_AS31499_2BoIdLV94NnrtvwbVNk89RkG6Wg86FBLjO2lzCH6o8FmebjrQv?input=http://bluesystem.ru/
        {
            "body_match": "<title>block-system</title>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T075609Z_AS0_HUKpvO8jhpAAdqfvJAlNqtoJOpDUf0MNDCQGuD1yJU2KsSUzxO?input=http://bluesystem.ru/
        {
            "body_match": "<title>Federal block</title>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200426T030624Z_AS15378_m3QsGmFgaY0yex11nq2wFgOTNLHiCK0lmShNdYZR6LXBKE1iq5?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://blocked.as20764.net/blocked.php",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200214T003928Z_AS16345_MspHYIbQka8Krh8T1rYKMv2a2mwRaYQZSVlKwgYpew7x3I1f4x?input=http://www.deti-404.com/
        {
            "body_match": "http://www.beeline.ru/customers/help/safe-beeline/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190904T071904Z_AS50473_nDaX3gMXRvqiOIIsQasGCrlo1mkiNiDIdRWwEVetB6AyQSlBDM?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://block.ecotelecom.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191123T232848Z_AS15582_SGLjs47pfssBgI4Pmtqe6Q4D8JfPdw5M5i68ofgzUIKRtw7s9M?input=http://www.deti-404.com/
        {
            "header_name": "Location",
            "header_prefix": "http://blocked.akado.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T190102Z_AS15582_AN3pN6fRfLwsONN4y0GEgnGLXlIGPv9QDysJwLhzVv3PZw4Ujz?input=http://bluesystem.ru/",
        {
            "body_match": "UA-2468561-43",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T035524Z_AS30868_YNRgacl7Q5HcThofYIOQRl0Z0T00uxv1TnvOXqhzsM7165fN8W?input=http://bluesystem.ru/
        {
            "body_match": ".akado-ural.ru/web/rkn/site_blocked.css",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180317T130438Z_AS39087_UU6okQpeONhX0qrLfLdlKQeculY95MVSW1zY89UcbM4snfJPNN?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://rkn.pakt.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190603T211434Z_AS0_kxjMajdYmi5TXQlX4eA3fC0yf9puWMbkCK1QP8TcUSz4CoS0So?input=http://bluesystem.ru/
        {
            "body_match": "185.36.60.2/icons/logo.png",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180317T124213Z_AS5467_jYLepdiccPKELyLYmRNgvZ8KaaeGBz4JArbyfepClYbyg1EHJK?input=http://bluesystem.ru/
        {
            "body_match": "МФТИ-Телеком&nbsp;&nbsp;</td>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T222011Z_AS43404_jQgcHPhGKPE8KsqFe0Psx5228ciYSdUgH6KCjYMUq5CJk6f6ty?input=http://bluesystem.ru/
        {
            "body_match": "rkn.ucanet.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180317T131247Z_AS41268_VA5OAJGFFPBeOIRJUBeiSu1WdeRjOtw2Z0O5t0FyOKmvQZsuse?input=http://bluesystem.ru/
        {
            "body_match": "www.lanta-net.ru/zapret/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T073159Z_AS31566_N85quRr4romDzcXN4MZPiHCueUqZ0WBQGZdGq7tcJWEh32D7bz?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://www.skynet-kazan.com/_blocked.htm",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180317T162427Z_AS25515_5VmIHP6K59TMNgwYPVjJMsKM4a87URc7sbuvlZe7yb5a7Y83Rf?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "block.ip.center.rt.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200218T053707Z_AS48642_teIfdu9u5LoU76KCYMwyEQOk2qbfpJPmeSsiYL2KRMgkYxwE9e?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://block.k-telecom.org",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180317T133059Z_AS196949_VIOHLwGOwFJGNHcWbbYtxOFTrTftiYhDXtyngllWDEmhgNgED1?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://forbidden.podryad.tv",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191004T205146Z_AS12714_Vh5wOEj1bL4YyQCNz2kUOmL6y3NSnP9DTAvn55eFd93q9YPfxr?input=http://www.thegailygrind.com/
        {
            "header_name": "Location",
            "header_prefix": "http://blocked.netbynet.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200314T210106Z_AS12714_rgCGaX2LPl458FfUVVwaldIdd0JwkrxzQzkkX7QRrlVVj2edPq?input=http://www.lesbi.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://blocked.ti.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190801T112858Z_AS205638_WIDlbpcLq2Wdx6ZuLHvDPyEiOfmcowETD2feCnGdfp4waZKUNa?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "https://blocked.tinkoff.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T050632Z_AS41560_b7QCibF5I8GA0EwSDSdRmMlISrxgZ4vc98irCf5uGRpC6uoAIm?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://blocked.ugmk-telecom.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190803T194713Z_AS47939_8XZsen8o7UM56nyowpxdQINGWBeWr4soyFi9C31IFEVv24Tg3R?input=http://www.deti-404.com/
        {
            "header_name": "Location",
            "header_prefix": "http://block.yaltanet.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180330T151901Z_AS8905_eVr71AR4JRpJBtXOPRIUqIQmsjKK449XNgqADi6sSfD1pL0uMI?input=http://bluesystem.ru/
        {
          "header_name": "Location",
          "header_prefix": "http://deny.cifra1.ru",
          "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200127T101808Z_AS8334_CXzMxCcZGarpjw4h6HZod7C4ktkoXLShemHwxSJ1CptUcnDQqL?input=http://www.lesbi.ru/
        {
            "body_match": "almatel.ru/ajax/all.php?e=ott_forbidden_reg",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190817T194620Z_AS57093_GyP7oVw2nGeRpf8YINz9YgO7KnrXPONAdWRFHwjTWrk1tzzyRE?input=http://www.lesbi.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://erblock.crimea.com",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180430T004143Z_AS8334_w0W0QB8R1vcxsb8GkwBu0vuI5LV4ktuldUTUvI2DLeEulIOxN3?input=http://bluesystem.ru/
        {
            "body_match": "GTM-NBL6CQ",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200215T074314Z_AS25159_0xrGzNzvnnsXSAVKwYNzwIb7cL2eUxH2Nj1fJ0nclVrYPQJmLO?input=http://www.deti-404.com/
        {
            "header_name": "Location",
            "header_prefix": "https://forbidden.yota.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180321T164414Z_AS47395_zANSZBCvk6wkOGQSCgFy5DVvM0X1akRXBjXkyazUrqFKY3JE53?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://forbidden.yota.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190221T004849Z_AS47395_EyAG1vxiNO1VkgbiIifh1zdrQ8Olgs4ntIfEeHpkuJozkjwFQZ?input=http://bluesystem.ru/
        {
            "body_match": "UA-16019436-1",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190215T191020Z_AS51077_PgHDPvuTuN4HiRIfg8b6bYw2J3diS2doqaQpqs8NLlPaBsC9XQ?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "https://cacti.telincom.ru/blocked.html",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180317T134334Z_AS56476_KFg0mIozfedCjgfrcGis7ZiFKnZn2gMg2BFxMpZMdxuIiVA0Vk?input=http://bluesystem.ru/
        {
            "body_match": "rkn.clkon.net/images/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200205T012112Z_AS8369_lz479luPP9r7txwbYi3IxOSC4J2m3eu2xPZbed1O5NTBq2cDQW?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "https://you-shall-not-pass.is74.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190726T044441Z_AS8369_pt6iOTfKLtNs6vy19VFsbMTvwtRno87AZ601Xdyj4TJkiwumfU?input=http://bluesystem.ru/
        {
            "body_match": "id=com.intersvyaz.lk&referrer=utm_source%3Dlp_you_shall_not_pass_parking",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180318T095622Z_AS50477_cLI1EK0sH5N5MEKzozCK1pZPygYAOWsfjxXhRB1BBIRGGDMk5J?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://sv-en.ru/block.php",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191123T161807Z_AS31195_eBzph7e3WZ0EhpiNDOVYeSjnVpAyR7DA8e5xW3e4U2yGB0LzZr?input=http://www.deti-404.com/
        {
            "body_match": "UA-97554836-1",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200118T012925Z_AS31213_HXkdYCWN5qqPLgvSvFam2G3EwubT2qtm6Wrp6e6s7GS8X46mDq?input=http://bluesystem.ru/
        {
            "body_match": "GTM-WBQ8X7M",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200215T053350Z_AS31208_ilgbksUk8hWR5svFbpJ0oxOkeDWdQqaW2xsDiL13G2VeN7KnVT?input=http://www.lesbi.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://m.megafonpro.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191213T100614Z_AS25159_ZHdmlcy3Gqv7zZKgNCUHU7kdmIRP9wsQ0xnBiRrEo5SUs0O5Zj?input=http://bluesystem.ru/
        {
            "body_match": "href=\"rkn\">Отменить</a>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190417T083259Z_AS0_uSpocMEwsEZlkDtgVOumm4liHHCbBA6KhbGbJJFfEkkpFydnVU?input=http://www.deti-404.com/
        {
            "body_match": "id:43845029,",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20191014T032243Z_AS24955_PfJea2GTQ0zkg1IMtUmEVa8FnVbDTB8SmPrFc5zHGOr5HyMc1p?input=http://www.deti-404.com/
        {
            "header_name": "Location",
            "header_prefix": "https://www.ufanet.ru/blocking.html",
            "locality": "isp"
        },
        {
            "body_match": "zapret-info.prometey.me",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190606T115638Z_AS8359_1AxAk5m7nGRoC2uLKul3UzQhvjFxQhwfI5jpdEYqyegSAIghmh?input=http://instinctmagazine.com/
        {
            "header_name": "Location",
            "header_prefix": "http://unblock.mts.ru",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200809T060553Z_AS6697_WHViLvwEDfLrt3yRqACQW09MnDhCy6jynycEEfObNuAApaBTpv?input=https://vk.com/pramenofanarchy
        {
            "header_name": "Location",
            "header_prefix": "https://vk.com/blank.php?rkn=",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20190525T080819Z_AS24955_qQMrVJZWRoIbrZFkqSUgKpO7SVsWXKSfH9ZtiIGPGoIiuaths0?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://95.213.254.253",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180317T132423Z_AS51081_aZcek3lkL9VJGuaZN1Li0gUnBdcfjA0DDCM4Ed3lKvDWk24bK1?input=http://bluesystem.ru/
        {
            "header_name": "Location",
            "header_prefix": "http://block.runnet.ru",
            "locality": "local"
        },
        {"dns_full": "159.255.26.69", "locality": "general"},
        # https://explorer.ooni.org/measurement/20171003T161217Z_AS15599_eoh3aUHQ7NV5LwWDA3Br8Hf3FGcgxG3s8mjxFd40cSWcV5BL23?input=http://lgbt.foundation/
        {"dns_full": "193.58.251.1", "locality": "general"},
        {"dns_full": "193.58.251.11", "locality": "general"},
        {"dns_full": "95.217.66.240", "locality": "general"},
        # https://explorer.ooni.org/measurement/20180919T192809Z_AS34984_Rlb0RqQAPfo5LqUQHWREV7c1sxNXcHSGHrVftNTgOoVBhAcu20?input=http://www.exgay.com
        {"dns_full": "93.158.134.250", "locality": "general"},
        {"dns_full": "217.148.54.171", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20190628T034744Z_AS35807_4XwiNixlQ8odJ6ek21IUmKwtvCecSOWoII5ZjwqzCCgx6Sx9a3?input=http://bluesystem.ru/
        {"dns_full": "185.37.129.10", "locality": "isp"},
        {"dns_full": "46.175.31.250", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20200318T090603Z_AS8641_sZfld8WLVRMRZ6Oa6uj23WNddUJ5zFCFLL5JCNBqorFDn1P050?input=http://www.lesbi.ru/
        {"dns_full": "46.175.31.250", "locality": "isp"},
        {"dns_full": "83.69.208.124", "locality": "isp"},
        {"dns_full": "212.1.226.59", "locality": "isp"},
        {"dns_full": "37.44.40.254", "locality": "isp"},
        {"dns_full": "87.241.223.133", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20180313T233202Z_AS51645_dIEFx0okmP7iqOXN3x1p97EObb6Z1oLDQYOHFLVvfn7c0FKRW6?input=http://bluesystem.ru/
        {"dns_full": "5.3.3.17", "locality": "isp"},
        # https://explorer.ooni.org/measurement/20180315T174422Z_AS12688_7Iy8vwd6JYREOl2E6E1PJnNeCVGVKlORQNYhUJ2tKyiWjaEFkY?input=http:%2F%2Fmaidanua.org%2F
        {"dns_full": "62.33.207.196", "locality": "country"},
        {"dns_full": "62.33.207.197", "locality": "country"},
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
        },
        # https://explorer.ooni.org/measurement/20180711T082508Z_AS15505_oTsIWsdnymUNFDsNnrCRIBb7hKzhU2GzmYv04oZvlUwQ2TicqG?input=http://gaytoday.com
        {
            "body_match": "://blocking-web-server.isu.net.sa/",
            "locality": "local"
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
        },
        # https://explorer.ooni.org/measurement/20181108T073326Z_AS33788_ZqpA2lJ2Rhs9pcjwp4fOIoDqNUMynmyBI5YKkaZI3c1HfDK1su?input=http://www.gayscape.com
        {
            "body_match": "/webadmin/deny/ptra/blocking.html",
            "locality": "isp"
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
    "TH": [
        # https://explorer.ooni.org/measurement/20190904T062730Z_AS7470_IqwbYni159FTGxsg003mQv3LKQZAW5MefvhKkBNcfvz9Ff5FBx?input=http://www.gboysiam.com/
        {
            "body_match": "Sorry. Access to this website has been disabled because the Ministry of Digital Economic",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20190911T075509Z_AS9931_nxPKYSoZ3cDyjEkfs8kHGRW4DpctE8wJfgXMKoMOWFwER1YTD7?input=http://www.gboysiam.com/",
        {
            "header_name": "Location",
            "header_prefix": "http://103.86.50.16",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20190101T072530Z_AS7470_TWZ0f5svDKrU2gYh3tmmboIGn8iTDkRaLaZD4oZq3iuSZbBTUm?input=http://www.gboysiam.com
        {
            "header_name": "Location",
            "header_prefix": "http://103.208.24.21",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20190101T072530Z_AS7470_TWZ0f5svDKrU2gYh3tmmboIGn8iTDkRaLaZD4oZq3iuSZbBTUm?input=http://www.gboysiam.com
        {
            "header_name": "Location",
            "header_prefix": "http://103.208.24.21",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20200214T212342Z_AS133481_bLNPUx39hgpO75VcUdF2V6pPXdiKoyug5hCio1HCMntxh7VaW7?input=http://www.gboysiam.com/
        {
            "header_name": "Location",
            "header_prefix": "http://prohibit.ais-idc.com",
            "locality": "country"
        },
        {
            "body_match": "pPGh0bWwgeG1sbnM6dj0idXJuOnNjaGVtYXMtbWljcm9zb2Z0LWNvbTp2bWwiDQp4bWxuczpvPSJ1cm46c",
            "locality": "country"
        },
        # https://explorer.ooni.org/measurement/20200213T120219Z_AS24378_W6w9AwtqzGx0p9Rr4O83ktxhRHZJk9lQWutj6k5bndi208V4lA?input=http://www.gboysiam.com/
        {
            "body_match": "http://124.40.225.20/?accessurl=",
            "locality": "isp"
        },
        {
            "body_match": "http://103.208.24.21/?accessurl=",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190314T223836Z_AS45758_saZmEbyWARgKDPY5FS8JmbrexGQAUUAHO0naE3K4jqMrEPuVfD?input=http://instinctmagazine.com/
        {
            "header_name": "Location",
            "header_prefix": "http://110.164.252.137/wpwarn/soft_bd/wpcbt_res.php",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20201228T234534Z_webconnectivity_TH_131445_n1_deRHboYpdtGToSqk?input=http://www.bbc.com/news/world-asia-38126928/
        {"dns_full": "125.26.170.3", "locality": "country"},
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
        },
        # https://explorer.ooni.org/measurement/20200207T075356Z_AS20978_JJ3svMeHEnIrFcIceAHeqrbp6RyDtgBqTtnDmo3mRfMEGFGiXK?input=http://transsexual.org/
        {
            "header_name": "Location",
            "header_prefix": "http://bilgi.turktelekom.com.tr/guvenli_internet_uyari",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190724T152019Z_AS13280_5XchAx4T8ZNmgtqbFSgcjHFB9QKFqviPSJa88PQs4VXCdk1mBo?input=http://www.gayscape.com/
        {
            "body_match": "To turn this off, you must verify your age - click below to log in to My3",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20200207T075356Z_AS20978_JJ3svMeHEnIrFcIceAHeqrbp6RyDtgBqTtnDmo3mRfMEGFGiXK?input=http://transsexual.org/
        {
            "body_match": "<title>Güvenli İnternet Uyarı</title>",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20180403T183403Z_AS9121_FfHjDmPkC0E5UoU3JMZoXJ2KRrMVyqdeTkHchmGEqAonEU64u4?input=http:%2F%2Fbeeg.com
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
    "UG": [
        # https://explorer.ooni.org/measurement/20190603T052310Z_AS12491_gPTKEWF0N9k2UpuLPVm6jl5q0ya6uTYge6iB2b0oXPcFejuhpc?input=http://www.gayhealth.com/
        {
            "body_match": "According to UCC regulation, Pornography pages are restricted for browsing.",
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

        # https://explorer.ooni.org/measurement/20190205T194537Z_AS26638_xu2k6ZPnY9mHgeu3M6qgVGf1Q192E12OFtcpztNMDBleHkEJPM?input=http://www.grindr.com/
        {
            "body_match": "https://staff.mpls.k12.mn.us/Depts/its/Pages/Block-Unblock-Requests.aspx",
            "locality": "local"
        },
        # https://explorer.ooni.org/measurement/20190321T164529Z_AS26661_gKN3hndB81x3e95ICECH0M7NVbk89s4pelMSjXFE3m89oA2F7p?input=http://www.gayegypt.com/
        {
            "body_match": "Jeffco Schools Internet Filtering Page",
            "locality": "local"
        }
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
    "YE": [
        {
            "body_match": "http://82.114.160.94/webadmin/deny/",
            "locality": "isp"
        },
        # https://explorer.ooni.org/measurement/20190104T220611Z_AS30873_kt947qO6Y9Hl4z6vwpmVq7G4psKKkNjEhJffySOv7sDGYoRbgZ?input=http://amygoodloe.com/lesbian-dot-org/",
        {
            "body_match": "http://deny.yemen.net.ye/webadmin/deny",
            "locality": "isp"
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
        # https://explorer.ooni.org/measurement/20190824T132919Z_AS5650_gwWRIicciG8fgrTzTFnuvsmlAHFOWgiAIAuDeL9RgH05TQsY3L?input=http://www.samesexmarriage.ca/
        {"dns_full": "185.228.168.254", "locality": "general"},
        {"dns_full": "207.246.127.171", "locality": "general"},
        {"dns_full": "45.77.77.148", "locality": "general"},
        # https://explorer.ooni.org/measurement/20180212T093619Z_AS12874_ivZ63xkT6Tqmlz8SyoIsbdkQNfN85CyNZTO1ZVeYTZFRh24xb8?input=http://www.gayscape.com
        {"dns_full": "185.236.104.104", "locality": "general"},
        {"dns_full": "54.242.237.204", "locality": "general"},
        {"dns_full": "45.32.203.129", "locality": "general"},
        {"dns_full": "3.93.224.57", "locality": "general"},
        {"dns_full": "52.206.227.167", "locality": "general"},
        # https://explorer.ooni.org/measurement/20191115T114711Z_AS12390_NIVFbxg8nx3pPxL5vbk2Fg4duFANRINLyvIaMNuzyDPiMdY2X3?input=https://bisexual.org/
        {"dns_full": "195.46.39.11", "locality": "general"},
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
