# 만세력 기반 사주 계산 모듈

# ─── 천간 ────────────────────────────────────────────────────────────
CHEONGAN = [
    {"name":"갑","hanja":"甲","oheng":"목","umyang":"양"},
    {"name":"을","hanja":"乙","oheng":"목","umyang":"음"},
    {"name":"병","hanja":"丙","oheng":"화","umyang":"양"},
    {"name":"정","hanja":"丁","oheng":"화","umyang":"음"},
    {"name":"무","hanja":"戊","oheng":"토","umyang":"양"},
    {"name":"기","hanja":"己","oheng":"토","umyang":"음"},
    {"name":"경","hanja":"庚","oheng":"금","umyang":"양"},
    {"name":"신","hanja":"辛","oheng":"금","umyang":"음"},
    {"name":"임","hanja":"壬","oheng":"수","umyang":"양"},
    {"name":"계","hanja":"癸","oheng":"수","umyang":"음"},
]

# ─── 지지 ────────────────────────────────────────────────────────────
JIJI = [
    {"name":"자","hanja":"子","oheng":"수","umyang":"양","animal":"쥐"},
    {"name":"축","hanja":"丑","oheng":"토","umyang":"음","animal":"소"},
    {"name":"인","hanja":"寅","oheng":"목","umyang":"양","animal":"호랑이"},
    {"name":"묘","hanja":"卯","oheng":"목","umyang":"음","animal":"토끼"},
    {"name":"진","hanja":"辰","oheng":"토","umyang":"양","animal":"용"},
    {"name":"사","hanja":"巳","oheng":"화","umyang":"음","animal":"뱀"},
    {"name":"오","hanja":"午","oheng":"화","umyang":"양","animal":"말"},
    {"name":"미","hanja":"未","oheng":"토","umyang":"음","animal":"양"},
    {"name":"신","hanja":"申","oheng":"금","umyang":"양","animal":"원숭이"},
    {"name":"유","hanja":"酉","oheng":"금","umyang":"음","animal":"닭"},
    {"name":"술","hanja":"戌","oheng":"토","umyang":"양","animal":"개"},
    {"name":"해","hanja":"亥","oheng":"수","umyang":"음","animal":"돼지"},
]

# ─── 월건 기준표 (甲/己년 인월=丙, 乙/庚년 인월=戊, ...) ──────────────
MONTH_CG_BASE = {0:2, 1:4, 2:6, 3:8, 4:0, 5:2, 6:4, 7:6, 8:8, 9:0}

# ─── 시건 기준표 (甲/己일 자시=甲, 乙/庚일 자시=丙, ...) ──────────────
# 五鼠遁日法: 甲己→甲, 乙庚→丙, 丙辛→戊, 丁壬→庚, 戊癸→壬
HOUR_CG_BASE = [0, 2, 4, 6, 8, 0, 2, 4, 6, 8]

# ─── 연도별 정확한 입춘일 (1900~2050) ──────────────────────────────
IPCHUN_DAY = {
    1900:5,1901:4,1902:4,1903:5,1904:5,1905:4,1906:4,1907:5,1908:5,1909:4,
    1910:4,1911:5,1912:5,1913:4,1914:4,1915:5,1916:5,1917:4,1918:4,1919:5,
    1920:5,1921:4,1922:4,1923:5,1924:5,1925:4,1926:4,1927:5,1928:5,1929:4,
    1930:4,1931:4,1932:5,1933:4,1934:4,1935:4,1936:5,1937:4,1938:4,1939:4,
    1940:5,1941:4,1942:4,1943:4,1944:5,1945:4,1946:4,1947:4,1948:5,1949:4,
    1950:4,1951:4,1952:5,1953:4,1954:4,1955:4,1956:5,1957:4,1958:4,1959:4,
    1960:5,1961:4,1962:4,1963:4,1964:5,1965:4,1966:4,1967:4,1968:5,1969:4,
    1970:4,1971:4,1972:4,1973:4,1974:4,1975:4,1976:4,1977:4,1978:4,1979:4,
    1980:5,1981:4,1982:4,1983:4,1984:4,1985:4,1986:4,1987:4,1988:4,1989:4,
    1990:4,1991:4,1992:4,1993:4,1994:4,1995:4,1996:4,1997:4,1998:4,1999:4,
    2000:4,2001:4,2002:4,2003:4,2004:4,2005:4,2006:4,2007:4,2008:4,2009:4,
    2010:4,2011:4,2012:4,2013:4,2014:4,2015:4,2016:4,2017:3,2018:4,2019:4,
    2020:4,2021:3,2022:4,2023:4,2024:4,2025:3,2026:4,2027:4,2028:4,2029:3,
    2030:4,2031:4,2032:4,2033:3,2034:4,2035:4,2036:4,2037:3,2038:4,2039:4,
    2040:4,2041:3,2042:4,2043:4,2044:4,2045:3,2046:4,2047:4,2048:4,2049:3,
    2050:4,
}

def _ipchun(year):
    return IPCHUN_DAY.get(year, 4)

# ─── 절기 기준 월 경계 (양력 기준 대략) ─────────────────────────────
MONTH_BOUNDARIES = [
    (1,6),(2,4),(3,6),(4,5),(5,6),(6,6),
    (7,7),(8,7),(9,8),(10,8),(11,7),(12,7)
]

def get_month_index(month, day):
    """절기 기준 월지 인덱스 반환 (子=0, 丑=1, 寅=2, ...)"""
    boundary_day = MONTH_BOUNDARIES[month-1][1]
    m = month if day >= boundary_day else month - 1
    return m % 12

def get_year_pillar(year, month, day):
    """년주 계산 — 연도별 정확한 입춘일 기준으로 사주년도 결정"""
    ipchun = _ipchun(year)
    saju_year = year - 1 if (month < 2 or (month == 2 and day < ipchun)) else year
    cg_idx = (saju_year - 4) % 10
    jj_idx = (saju_year - 4) % 12
    return CHEONGAN[cg_idx], JIJI[jj_idx], saju_year

def get_month_pillar(saju_year, month, day):
    """월주 계산"""
    year_cg_idx = (saju_year - 4) % 10
    base = MONTH_CG_BASE[year_cg_idx]
    month_jj_idx = get_month_index(month, day)
    # (월지 - 2) % 12 로 인월(index=2)을 0번으로 정규화한 뒤 월건 계산
    month_cg_idx = (base + (month_jj_idx - 2) % 12) % 10
    return CHEONGAN[month_cg_idx], JIJI[month_jj_idx]

def get_day_pillar(year, month, day):
    """일주 계산 — 1900-01-31 = 甲子日 기준"""
    import datetime
    # 1900-01-01 기준 delta, 이 날은 甲午日(index=30)
    # 甲子(index=0)는 1900-01-31이므로 地支 offset = (-30 mod 12) = 6
    base_date = datetime.date(1900, 1, 1)
    delta = (datetime.date(year, month, day) - base_date).days
    cg_idx = (delta + 0) % 10
    jj_idx = (delta + 6) % 12
    return CHEONGAN[cg_idx], JIJI[jj_idx]

def get_hour_pillar(day_cg_idx, hour_24):
    """시주 계산 — 五鼠遁日法"""
    # 자시(子時): 23:00~01:00
    if hour_24 == 23 or hour_24 == 0:
        jj_idx = 0
    else:
        jj_idx = ((hour_24 + 1) // 2) % 12
    base = HOUR_CG_BASE[day_cg_idx % 10]
    cg_idx = (base + jj_idx) % 10
    return CHEONGAN[cg_idx], JIJI[jj_idx]

def convert_to_24h(hour, ampm):
    """오전/오후 → 24시간"""
    if ampm == "오전":
        return hour if hour != 12 else 0
    else:
        return hour + 12 if hour != 12 else 12

def lunar_to_solar(year, month, day, leap=False):
    """음력→양력 변환"""
    import datetime
    try:
        from korean_lunar_calendar import KoreanLunarCalendar
        cal = KoreanLunarCalendar()
        cal.setLunarDate(year, month, day, bool(leap))
        return cal.solarYear, cal.solarMonth, cal.solarDay
    except Exception:
        # 라이브러리 없을 경우 근사치 (+30일)
        try:
            solar = datetime.date(year, month, day) + datetime.timedelta(days=30)
            return solar.year, solar.month, solar.day
        except Exception:
            return year, month, day

def calc_saju(year, month, day, hour=None, ampm=None):
    """사주팔자 계산 메인 함수"""
    year_cg, year_jj, saju_year = get_year_pillar(year, month, day)
    month_cg, month_jj = get_month_pillar(saju_year, month, day)
    day_cg, day_jj = get_day_pillar(year, month, day)

    saju_flat = {
        "년주천간": year_cg,
        "년주지지": year_jj,
        "월주천간": month_cg,
        "월주지지": month_jj,
        "일주천간": day_cg,
        "일주지지": day_jj,
    }

    parts = [
        f"{year_cg['hanja']}{year_jj['hanja']}",
        f"{month_cg['hanja']}{month_jj['hanja']}",
        f"{day_cg['hanja']}{day_jj['hanja']}",
    ]

    if hour is not None and ampm is not None:
        hour_24 = convert_to_24h(hour, ampm)
        day_cg_idx = CHEONGAN.index(day_cg)
        hour_cg, hour_jj = get_hour_pillar(day_cg_idx, hour_24)
        saju_flat["시주천간"] = hour_cg
        saju_flat["시주지지"] = hour_jj
        parts.append(f"{hour_cg['hanja']}{hour_jj['hanja']}")
    else:
        saju_flat["시주천간"] = None
        saju_flat["시주지지"] = None

    saju_str = " / ".join(parts)
    return saju_flat, saju_str
