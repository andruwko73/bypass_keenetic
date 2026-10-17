"""Shared lightweight policy used by HTTP custom-service probes."""


CUSTOM_TARGET_DENY_MARKERS = (
    'unsupported_country_region_territory',
    'country, region, or territory not supported',
    'app-unavailable-in-region',
    'unavailable in region',
    'unavailable-in-region',
    'not available in your region',
    'request not allowed',
)


# Official ChatGPT regions, checked 2026-10-17:
# https://help.openai.com/en/articles/7947663-chatgpt-supported-countries
# Pro Dots excludes EEA + GB + CH:
# https://help.openai.com/en/articles/20001530-getting-started-with-your-dot
CHATGPT_SUPPORTED_REGIONS = frozenset('''
AL DZ AF AX AD AO AG AR AM AW AU AT AZ BS BH BD BB BE BZ BM BJ BT BO BA BW BR BN BG BF BI
CV KH CM CA KY CF TD CL CO KM CG CD CR CI HR CY CZ DK DJ DM DO EC EG SV GQ ER EE SZ ET
FO FJ FI FR GF PF TF GA GM GE DE GH GR GD GL GT GP GN GW GY HT VA HN HU IS IN ID IQ IE
IL IT JM JP JO KZ KE KI KW KG LA LV LB LS LR LY LI LT LU MG MW MY MV ML MT MH MQ MR MU
YT MX FM MD MC MN ME MA MZ MM NA NR NP NL NC NZ NI NE NG MK NO OM PK PW PS PA PG PY PE
PH PL PT QA RE RO RW BL SH KN LC MF PM VC WS SM ST SA SN RS SC SL SG SK SI SB SO ZA KR
SS ES LK SR SE CH SD SJ TW TJ TZ TH TL TG TO TT TN TR TM TV UG UA AE GB US UY UZ VU VN
WF YE ZM ZW
'''.split())
DOTS_PRO_EXCLUDED_REGIONS = frozenset('''
AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE
IS LI NO GB CH AX GF GP MQ RE YT MF
'''.split())

CHATGPT_DOTS_HOSTS = frozenset(('chatgpt.com', 'chat.openai.com', 'api.openai.com'))
DOTS_TRACE_URL = 'https://chatgpt.com/cdn-cgi/trace'


def dots_pro_region_verdict(data):
    fields = dict(line.split('=', 1) for line in data[:4096].decode('ascii', errors='ignore').splitlines() if '=' in line)
    country = fields.get('loc', '').strip().upper()
    if (fields.get('h') != 'chatgpt.com' or country in ('XX', 'ZZ')
            or len(country) != 2 or not country.isascii() or not country.isalpha()):
        return None, 'Dots Pro: регион выхода не определён.'
    if country not in CHATGPT_SUPPORTED_REGIONS or country in DOTS_PRO_EXCLUDED_REGIONS:
        return False, f'Dots Pro: регион {country} не поддерживается.'
    return True, f'Dots Pro: регион {country} допустим; доступ аккаунта проверяется отдельно.'
