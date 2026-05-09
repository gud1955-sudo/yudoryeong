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

# ─── 절기 기준 월 경계 (양력 기준 대략) ─────────────────────────────
# 각 월의 절기 시작일: 소한(1/6), 입춘(2/4), 경칩(3/6), 청명(4/5), ...
MONTH_BOUNDARIES = [
    (1,6),(2,4),(3,6),(4,5),(5,6),(6,6),
    (7,7),(8,7),(9,8),(10,8),(11,7),(12,7)
]

def get_month_index(month, day):
    """절기 기준 월지 인덱스 반환 (子=0, 丑=1, 寅=2, ...)"""
    boundary_day = MONTH_BOUNDARIES[month-1][1]
    m = month if day >= boundary_day else month - 1
    return m % 12  # 12월 대설 이후 → 0(子月), 1월 소한 이후 → 1(丑月), 입춘 이후 → 2(寅月)

def get_year_pillar(year, month, day):
    """년주 계산 — 입춘(2월 4일) 기준으로 사주년도 결정"""
    # 입춘 이전 출생이면 전년도로 취급
    saju_year = year - 1 if (month < 2 or (month == 2 and day < 4)) else year
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
