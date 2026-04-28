import os
import re
import hashlib
import traceback
from datetime import date as _date

from flask import Flask, request, jsonify, render_template
import requests
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# ─── 천간·지지 상수 ──────────────────────────────────────────────
_CHEONGAN = [
    {'hanja': '甲', 'hangul': '갑', 'oheng': '목'},
    {'hanja': '乙', 'hangul': '을', 'oheng': '목'},
    {'hanja': '丙', 'hangul': '병', 'oheng': '화'},
    {'hanja': '丁', 'hangul': '정', 'oheng': '화'},
    {'hanja': '戊', 'hangul': '무', 'oheng': '토'},
    {'hanja': '己', 'hangul': '기', 'oheng': '토'},
    {'hanja': '庚', 'hangul': '경', 'oheng': '금'},
    {'hanja': '辛', 'hangul': '신', 'oheng': '금'},
    {'hanja': '壬', 'hangul': '임', 'oheng': '수'},
    {'hanja': '癸', 'hangul': '계', 'oheng': '수'},
]

_JIJI = [
    {'hanja': '子', 'hangul': '자', 'oheng': '수'},
    {'hanja': '丑', 'hangul': '축', 'oheng': '토'},
    {'hanja': '寅', 'hangul': '인', 'oheng': '목'},
    {'hanja': '卯', 'hangul': '묘', 'oheng': '목'},
    {'hanja': '辰', 'hangul': '진', 'oheng': '토'},
    {'hanja': '巳', 'hangul': '사', 'oheng': '화'},
    {'hanja': '午', 'hangul': '오', 'oheng': '화'},
    {'hanja': '未', 'hangul': '미', 'oheng': '토'},
    {'hanja': '申', 'hangul': '신', 'oheng': '금'},
    {'hanja': '酉', 'hangul': '유', 'oheng': '금'},
    {'hanja': '戌', 'hangul': '술', 'oheng': '토'},
    {'hanja': '亥', 'hangul': '해', 'oheng': '수'},
]

# 절기 근사 날짜 (월, 일) → 해당 월지지 시작일
_JEOLGI_DATES = [
    (1,  6),  # 소한 → 丑月(1)
    (2,  4),  # 입춘 → 寅月(2)
    (3,  6),  # 경칩 → 卯月(3)
    (4,  5),  # 청명 → 辰月(4)
    (5,  6),  # 입하 → 巳月(5)
    (6,  6),  # 망종 → 午月(6)
    (7,  7),  # 소서 → 未月(7)
    (8,  7),  # 입추 → 申月(8)
    (9,  8),  # 백로 → 酉月(9)
    (10, 8),  # 한로 → 戌月(10)
    (11, 7),  # 입동 → 亥月(11)
    (12, 7),  # 대설 → 子月(0)
]
_JEOLGI_JIJI = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0]

_DAY60_BASE = _date(1900, 1, 31)  # 甲子日 기준점

_GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro",
]
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


# ─── 유틸 함수 ────────────────────────────────────────────────────

def _get_month_branch(year, month, day):
    """절기 근사 기반 월지지 인덱스 반환"""
    for i in range(11, -1, -1):
        m, d = _JEOLGI_DATES[i]
        if month > m or (month == m and day >= d):
            return _JEOLGI_JIJI[i]
    return 0  # 1월 1~5일: 子月


def lunar_to_solar(year, month, day, leap=False):
    """음력 → 양력 변환"""
    try:
        from korean_lunar_calendar import KoreanLunarCalendar
        cal = KoreanLunarCalendar()
        cal.setLunarDate(year, month, day, bool(leap))
        return cal.solarYear, cal.solarMonth, cal.solarDay
    except Exception:
        from datetime import timedelta
        d = _date(year, month, min(day, 28)) + timedelta(days=30)
        return d.year, d.month, d.day


def calc_saju(year, month, day, hour=None, ampm=None):
    """사주팔자 계산. hour=1~12, ampm='오전'|'오후'"""
    # 24시간 변환
    hour_24 = None
    if hour is not None:
        if ampm == '오후' and hour != 12:
            hour_24 = hour + 12
        elif ampm == '오전' and hour == 12:
            hour_24 = 0
        else:
            hour_24 = hour

    # 년주 (입춘 기준)
    saju_year = year
    if month < 2 or (month == 2 and day < 4):
        saju_year = year - 1
    year_idx     = (saju_year - 4) % 60
    year_gan_idx = year_idx % 10
    year_ji_idx  = year_idx % 12
    year_gan = _CHEONGAN[year_gan_idx]
    year_ji  = _JIJI[year_ji_idx]

    # 월주 (절기 기준)
    month_ji_idx = _get_month_branch(year, month, day)
    month_num    = (month_ji_idx - 2) % 12          # 인월=0 기준
    month_start  = [2, 4, 6, 8, 0, 2, 4, 6, 8, 0][year_gan_idx]
    month_gan_idx = (month_start + month_num) % 10
    month_gan = _CHEONGAN[month_gan_idx]
    month_ji  = _JIJI[month_ji_idx]

    # 일주
    day_idx     = (_date(year, month, day) - _DAY60_BASE).days % 60
    day_gan_idx = day_idx % 10
    day_ji_idx  = day_idx % 12
    day_gan = _CHEONGAN[day_gan_idx]
    day_ji  = _JIJI[day_ji_idx]

    # 시주
    hour_gan = hour_ji = None
    if hour_24 is not None:
        hour_ji_idx  = (hour_24 + 1) // 2 % 12
        hour_start   = [0, 2, 4, 6, 8][day_gan_idx % 5]
        hour_gan_idx = (hour_start + hour_ji_idx) % 10
        hour_gan = _CHEONGAN[hour_gan_idx]
        hour_ji  = _JIJI[hour_ji_idx]

    saju_flat = {
        '년주천간': year_gan,
        '년주지지': year_ji,
        '월주천간': month_gan,
        '월주지지': month_ji,
        '일주천간': day_gan,
        '일주지지': day_ji,
    }
    if hour_gan:
        saju_flat['시주천간'] = hour_gan
        saju_flat['시주지지'] = hour_ji

    # 오행 분포 계산
    oheng_count = {'목': 0, '화': 0, '토': 0, '금': 0, '수': 0}
    for key in ['년주천간', '년주지지', '월주천간', '월주지지', '일주천간', '일주지지']:
        oheng_count[saju_flat[key]['oheng']] += 1
    if hour_gan:
        oheng_count[hour_gan['oheng']] += 1
        oheng_count[hour_ji['oheng']]  += 1

    max_v = max(oheng_count.values())
    min_v = min(oheng_count.values())
    saju_flat['강한기운'] = '·'.join(k for k, v in oheng_count.items() if v == max_v)
    saju_flat['약한기운'] = '·'.join(k for k, v in oheng_count.items() if v == min_v)
    saju_flat['오행분포'] = oheng_count

    def fmt(g, j):
        return f"{g['hanja']}{j['hanja']}({g['hangul']}{j['hangul']})"

    parts = [
        fmt(year_gan, year_ji),
        fmt(month_gan, month_ji),
        fmt(day_gan, day_ji),
        fmt(hour_gan, hour_ji) if hour_gan else '시주미상',
    ]
    saju_str = ' / '.join(parts)

    return saju_flat, saju_str


def call_gemini(prompt, temperature=0.7):
    """Gemini API 호출 — 503 시 모델 순차 폴백 + 재시도"""
    import time as _time
    api_key = os.getenv('GEMINI_API_KEY', '')
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 없습니다.")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 8192,
        },
    }

    last_err = None
    for model in _GEMINI_MODELS:
        url = f"{_GEMINI_BASE.format(model=model)}?key={api_key}"
        for attempt in range(3):          # 모델당 최대 3회 재시도
            try:
                resp = requests.post(url, json=payload, timeout=120)
                if resp.status_code == 503:
                    _time.sleep(2 ** attempt)
                    last_err = resp.text
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data['candidates'][0]['content']['parts'][0]['text']
            except (requests.RequestException, KeyError) as e:
                last_err = str(e)
                _time.sleep(2 ** attempt)

    raise RuntimeError(f"모든 Gemini 모델 호출 실패: {last_err}")


def parse_birth_params(data):
    """요청 데이터에서 birth, time 파싱 (음력 변환 포함)"""
    birth = data.get('birth', '')
    time  = data.get('time', '모름')
    lunar = data.get('lunar', False)
    leap  = data.get('leap', False)
    if birth and lunar:
        try:
            y, m, d = [int(x) for x in birth.split('-')]
            sy, sm, sd = lunar_to_solar(y, m, d, leap)
            birth = f"{sy}-{sm:02d}-{sd:02d}"
        except Exception:
            pass
    return birth, time


def make_base_key(gender, birth, time):
    return hashlib.md5(f"{gender}|{birth}|{time}".encode()).hexdigest()


def make_detail_key(gender, birth, time):
    return hashlib.md5(f"detail|{gender}|{birth}|{time}".encode()).hexdigest()


def attach_nim(text, names):
    """이름 뒤에 '님' 자동 부착"""
    for name in names:
        if not name:
            continue
        text = re.sub(rf'{re.escape(name)}(?!님)', f'{name}님', text)
    return text


def trim_preview(text):
    """맛보기 텍스트를 3문장 이내로 축약"""
    text = text.strip()
    sentences = re.split(r'(?<=[.。!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return ' '.join(sentences[:3])


FULL_ANALYSIS_PROMPT = """
당신은 수십 년 경력의 명리학자 유도령이오.
의뢰인을 부를 때는 반드시 이름 뒤에 님을 붙이시오.

형식 규칙을 반드시 지키시오.

항목 대제목은 [번호. 항목명 — 이 사람의 일간·오행을 반영한 짧은 부제] 형식으로 쓰시오.
항목 안 소제목은 별도 줄에 짧은 문구로 쓰고, 바로 아래 줄부터 내용을 서술하시오.
소제목에 괄호, 기호, 번호를 붙이지 마시오.
별표(**), 이모지, 구분선, 하이픈(-) 목록, 숫자 목록은 절대 쓰지 마시오.
한자가 등장할 때만 괄호 안에 한글 독음을 병기하시오. 예) 庚金(경금), 丙午(병오)
이미 한국어인 단어에는 절대 괄호를 달지 마시오. 사주, 오행, 재물, 운세, 직업 같은 한국어 낱말 뒤에 같은 뜻의 한국어를 괄호로 반복하는 것은 금지이오.
명리학 전문 용어가 처음 등장할 때만 짧게 뜻풀이 하시오. 이미 설명한 용어는 다시 풀지 마시오.
각 항목의 내용이 다른 항목과 겹치지 않도록 하시오.
인공지능, AI, 데이터, 알고리즘 같은 단어는 절대 쓰지 마시오.

아래 6개 항목을 순서대로 작성하시오.

[1. 선천적 기질 및 성향 — 이 사람 일간을 반영한 부제를 여기에 쓰시오]

핵심 기질
일간의 오행과 음양을 중심으로 타고난 본질적 기질을 서술하시오.

심리 패턴
십신(十神)을 통해 드러나는 성격 장단점과 무의식적 행동 패턴을 짚으시오.

사회적 모습과 내면
타인에게 보이는 모습과 실제 내면의 차이를 서술하시오.

[2. 재물 및 경제운 — 이 사람 재성 배치를 반영한 부제를 여기에 쓰시오]

재물 그릇
정재(꾸준히 벌어들이는 돈)와 편재(한번에 크게 들어오는 돈)의 비율로 본 타고난 재물 규모와 돈을 모으는 방식을 서술하시오.

투자 성향
공격적 투자와 안정적 저축 중 이 사주에 맞는 재테크 방향을 사주 근거와 함께 서술하시오.

재물의 흐름
돈이 강하게 들어오는 시기와 지출을 단속해야 하는 시기, 평생 재물운의 큰 흐름을 서술하시오.

[3. 직업 및 커리어 — 이 사람 관성·식상 배치를 반영한 부제를 여기에 쓰시오]

천직과 유리한 분야
관성(직업·사회적 지위 기운)과 식상(재능·표현력 기운)으로 본 타고난 직업 적성과 유리한 산업군을 구체적으로 서술하시오.

직장 내 처세
상사·동료와의 관계성, 직장 생활과 사업 중 어느 쪽이 맞는지, 승진운을 짚으시오.

변화의 타이밍
이직이나 창업 등 변화를 주기에 에너지가 가장 좋은 시기를 서술하시오.

[4. 애정 및 인간관계 — 이 사람 배우자성 배치를 반영한 부제를 여기에 쓰시오]

연애 스타일
내가 끌리는 사람과 나에게 잘해주는 사람의 차이, 연애에서 반복되는 패턴을 서술하시오.

배우자운과 인연 시기
배우자성이 어디에 자리하는지, 인연이 나타나는 시기와 잘 맞는 상대의 오행·일간을 서술하시오.
결혼 후 가정운과 부부 관계의 특징도 짚으시오.

대인관계 솔루션
갈등이 생기기 쉬운 살(煞)이나 합(合) 관계를 짚고 관계 개선을 위한 구체적 조언을 서술하시오.

[5. 건강 및 라이프스타일 — 이 사람 오행 과다·결핍을 반영한 부제를 여기에 쓰시오]

취약한 신체 부위
오행의 과다와 결핍이 오장육부 중 어느 기관에 영향을 미치는지 서술하시오.

멘탈 관리
스트레스 취약 시기와 마음을 다스리는 방법을 짚으시오.

맞춤 개운법
부족한 기운을 채워주는 색상·숫자·방향·음식을 구체적으로 알려주시오.

[6. 주기별 상세 운세 — 이 사람 현재 대운을 반영한 부제를 여기에 쓰시오]

대운의 흐름
현재 대운(大運, 10년 단위로 바뀌는 인생의 큰 흐름)이 어디에 해당하는지, 그 기운이 삶에 어떻게 작용하는지 분석하시오.

2026년 길흉
2026년 병오년이 이 사주에 미치는 영향과 올해 행동 지침을 두세 문장으로 짚으시오.

인생의 골든타임
중요한 결정을 내리기에 가장 길한 시기가 언제인지 구체적으로 서술하시오.

최소 80줄 이상, 읽는 사람이 자신의 이야기라고 느낄 만큼 개인화된 감정서를 작성하시오.
각 항목은 서로 내용이 겹치지 않게 하시오.
마지막은 유도령이 이 사람의 삶 전체를 꿰뚫어 본 뒤 전하는 진심 어린 한 마디로 마무리하시오.
"""


SINN_PROMPT = """
당신은 수십 년 경력의 명리학자 유도령이오. 지금부터 의뢰인의 2026년 병오년 신년운세를 감정서 형식으로 풀어주시오.
의뢰인을 부를 때는 반드시 이름 뒤에 님을 붙여 호칭하시오. 예) 홍길동님, 김영희님. 절대 이름만 단독으로 쓰지 마시오.
이 감정서는 2026년 한 해의 운세 흐름에만 집중하시오. 타고난 성격·적성·평생운 분석은 절대 포함하지 마시오.
항목 제목은 [ ] 안에 표시하고, 본문은 자연스러운 문장으로 이어 쓰시오.
별표, 이모지, 구분선, 숫자 목록 등 일체의 기호는 절대 쓰지 마시오.
한자를 쓸 때는 반드시 괄호 안에 한글 독음을 병기하시오.
명리학 용어를 처음 등장할 때는 반드시 쉬운 말로 풀어 설명하시오. 예) 세운(그 해의 기운), 관성(직업·사회적 지위와 관련된 기운), 재성(돈·재물과 관련된 기운) 처럼 괄호 안에 일반인도 바로 이해할 수 있게 설명하시오.
각 항목의 내용이 다른 항목과 겹치지 않도록 하시오. 같은 내용을 반복하지 마시오.

[2026년 총운 — 병오년이 이 사주에 미치는 영향]

丙火(병화)가 이 사주 일간과 어떤 관계를 형성하는지 설명하시오.
午火(오화)가 기존 지지들과 어떤 작용을 일으키는지 분석하시오.
2026년이 이 사람에게 전반적으로 어떤 해인지 — 기회의 해인지, 안정의 해인지, 변화의 해인지 — 명확하게 짚어주시오.
올해 가장 강하게 작용하는 키워드 세 가지를 선정하고 각각 사주 근거와 함께 설명하시오.

[연애와 인연운]

올해 인연이 들어오는 시기를 월 단위로 구체적으로 짚어주시오.
현재 연인이 있다면 올해 관계의 흐름과 변곡점을, 없다면 인연이 시작될 가능성이 높은 달을 알려주시오.
결혼을 고민 중인 경우 올해 결혼 적합성 여부도 서술하시오.

[직업과 재물운]

올해 커리어 변화의 시기와 이직·창업·승진 기운이 오는 달을 알려주시오.
올해 재물이 강하게 들어오는 달과 지출·손실이 몰리는 달을 구체적으로 서술하시오.
투자나 계약 관련 판단을 내려야 한다면 어느 달이 좋고 어느 달이 위험한지 알려주시오.

[건강운]

올해 세운의 기운이 신체 어느 부위에 영향을 줄 수 있는지 분석하시오.
특히 조심해야 할 시기와 생활 습관을 서술하시오.

[월별 운세 — 1월부터 12월까지]

각 달의 기운을 분석하여 월별 운세를 서술하시오.
각 달은 최소 세 문장 이상으로 쓰고, 좋은 달과 주의할 달의 이유를 명확히 밝히시오.
위 항목들(연애·직업·재물·건강)에서 이미 언급한 내용을 그대로 반복하지 말고, 월별 세부 흐름을 새롭게 서술하시오.

[2026년 행운과 조언]

올해 행운의 방향, 색, 숫자를 알려주시오.
2026년을 가장 잘 보내기 위해 반드시 해야 할 것 두 가지와 반드시 피해야 할 것 두 가지를 서술하시오.

최소 70줄 이상, 읽는 사람이 자신의 2026년이 생생하게 보이는 것처럼 구체적으로 작성하시오.
각 항목은 서로 내용이 겹치지 않게 하고, 억지로 분량을 늘리지 마시오.
마지막은 유도령이 2026년을 앞둔 이 사람에게 전하는 따뜻하고 진심 어린 한 마디로 마무리하시오.
"""


GUNG_PROMPT = """
당신은 수십 년 경력의 명리학자 유도령이오. 지금부터 두 사람의 짝궁합을 감정서 형식으로 풀어주시오.
두 사람을 부를 때는 반드시 이름 뒤에 님을 붙여 호칭하시오. 예) 홍길동님, 김영희님. 절대 이름만 단독으로 쓰지 마시오.
이 감정서는 두 사람의 관계 궁합 분석에만 집중하시오. 각 개인의 성격이나 개인 운세 분석은 절대 포함하지 마시오.
항목 제목은 [ ] 안에 표시하고, 본문은 자연스러운 문장으로 이어 쓰시오.
별표, 이모지, 구분선, 숫자 목록 등 일체의 기호는 절대 쓰지 마시오.
한자를 쓸 때는 반드시 괄호 안에 한글 독음을 병기하시오.
명리학 용어를 처음 등장할 때는 반드시 쉬운 말로 풀어 설명하시오. 예) 일간(내 사주의 중심 글자), 상생(서로 도와주는 관계), 상극(서로 충돌하는 관계) 처럼 괄호 안에 일반인도 바로 이해할 수 있게 설명하시오.
각 항목의 내용이 다른 항목과 겹치지 않도록 하시오. 같은 내용을 반복하지 마시오.

[두 사주의 기운 — 첫인상과 끌림의 이유]

두 사람의 일간이 오행상 어떤 관계인지(상생·상극·비화)를 설명하고, 이것이 실제 관계에서 어떻게 나타나는지 서술하시오.
처음 만났을 때 서로가 끌리는 이유를 사주 근거로 설명하시오.
두 사람의 사주 에너지가 합쳐졌을 때 어떤 시너지가 생기고 어디서 마찰이 발생하는지 서술하시오.

[성격 궁합 — 함께 살아가는 방식]

두 사람의 성격이 일상에서 어떻게 충돌하고 어떻게 보완되는지 구체적인 상황으로 설명하시오.
한쪽의 강점이 다른 쪽의 약점을 채워주는 지점과, 반대로 서로를 자극하는 지점을 짚어주시오.
두 사람이 함께 있을 때 에너지가 올라가는 패턴과 소모되는 패턴을 서술하시오.

[연애 궁합 — 감정과 표현의 방식]

두 사람이 사랑을 표현하는 방식의 차이와 그 차이를 좁히는 방법을 설명하시오.
질투, 집착, 권태 등 연애에서 주의해야 할 요소들을 사주 근거와 함께 짚어주시오.
두 사람 사이에서 감정적으로 위기가 올 수 있는 시기와 그 이유를 서술하시오.

[결혼 궁합 — 장기적인 동반자로서의 적합성]

결혼 생활에서 두 사람의 역할 분담이 어떻게 이루어지는지 설명하시오.
경제관, 생활 리듬, 가치관의 궁합을 구체적으로 서술하시오.
자녀운과 가정의 안정성을 사주로 분석하시오.
이 관계가 오래갈수록 깊어지는 궁합인지, 초반 열정이 식으면 갈등이 커지는 구조인지 솔직하게 짚어주시오.

[2026년 이 커플의 운세]

병오년의 기운이 두 사람의 관계에 어떻게 작용하는지 분석하시오.
올해 두 사람 관계에서 중요한 전환점이 되는 달을 짚어주시오.
올해 커플에게 특히 좋은 달과 갈등이 커질 수 있는 달을 근거와 함께 알려주시오.

[궁합 점수와 총평]

연애 궁합, 결혼 궁합, 소통 궁합, 재물 궁합, 미래 궁합을 각각 100점 만점으로 평가하고 각 점수의 근거를 두 문장 이상으로 설명하시오.
종합 점수와 함께 이 궁합을 한 문장으로 정의하시오.
이 커플이 오래 행복하게 함께하기 위해 반드시 알아야 할 핵심 한 가지를 서술하시오.

최소 70줄 이상, 두 사람이 읽었을 때 서로를 더 깊이 이해하게 되는 감정서를 작성하시오.
각 항목은 서로 내용이 겹치지 않게 하고, 억지로 분량을 늘리지 마시오.
마지막은 유도령이 두 사람에게 직접 전하는, 이 인연에 대한 진심 어린 한 마디로 마무리하시오.
"""


# ─── 캐시 ────────────────────────────────────────────────────────
BASE_CACHE     = {}
DETAIL_CACHE   = {}
SINNYEON_CACHE = {}
GUNGHAP_CACHE  = {}


# ─── 정통사주 라우트 ──────────────────────────────────────────────
@app.route('/saju')
def saju_page():
    return render_template('saju_input.html')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    """무료 기본 사주 분석 - 사주팔자는 실제 만세력 계산, 맛보기만 Gemini"""
    data = request.json
    gender, name = data['gender'], data['name']
    birth, time = parse_birth_params(data)
    base_key = make_base_key(gender, birth, time)

    try:
        if base_key not in BASE_CACHE:
            # ── 1. 실제 만세력으로 사주팔자 계산 ──
            parts = birth.split('-')
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])

            hour, ampm = None, None
            if time != '모름':
                # "오전 10시 30분" 파싱
                am_match = re.search(r'(오전|오후)', time)
                h_match  = re.search(r'(\d+)시', time)
                if am_match and h_match:
                    ampm = am_match.group(1)
                    hour = int(h_match.group(1))

            saju_flat, saju_str = calc_saju(year, month, day, hour, ampm)

            # ── 2. 사주 원국 간단 해석 (무료 공개) ──
            ilgan = saju_flat.get('일주천간', {})
            prompt = f"""당신은 수십 년 경력의 명리학자 유도령이오. 위엄 있는 도사님 말투(~하오, ~이오)를 쓰시오.
이모지나 특수기호, 별표는 절대 쓰지 마시오.
의뢰인을 부를 때는 반드시 이름 뒤에 님을 붙이시오.
한자가 등장할 때만 괄호 안에 한글 독음을 병기하시오. 예) 庚金(경금)
이미 한국어인 단어 뒤에 같은 뜻의 한국어를 괄호로 달지 마시오. 예) 사주(사주팔자) — 금지.
인공지능, AI, 데이터 같은 단어는 절대 금지하오.

{name}님 사주팔자: {gender} / {birth} / {saju_str}
일간: {ilgan.get('hanja','?')}({ilgan.get('hangul','?')}) — {ilgan.get('oheng','?')}행

이 사주팔자 원국을 4~5문장으로 해석하시오.
팔자 전체의 기운, 오행 균형, 이 사람이 타고난 운명적 특징을 도사답게 짚어주시오.
전문 용어가 처음 나올 때만 짧게 뜻풀이 하시오.
마지막 문장은 반드시 이렇게 끝맺으시오: "재물·커리어·애정·건강·대운의 상세한 흐름은 감정서에 낱낱이 담겨 있소이다."
"""
            preview = call_gemini(prompt, temperature=0.6).strip()

            BASE_CACHE[base_key] = {
                'saju': saju_flat,
                'preview': preview,
                'saju_str': saju_str
            }

        cached = BASE_CACHE[base_key]
        return jsonify({
            'saju': cached['saju'],
            'preview': cached.get('preview', '')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/pay_analyze', methods=['POST'])
def pay_analyze():
    """결제 후 종합 사주 상세 분석"""
    data = request.json
    gender, name = data['gender'], data['name']
    birth, time = parse_birth_params(data)
    base_key   = make_base_key(gender, birth, time)
    detail_key = make_detail_key(gender, birth, time)
    try:
        if base_key not in BASE_CACHE:
            parts = birth.split('-')
            yr, mo, dy = int(parts[0]), int(parts[1]), int(parts[2])
            hour, ampm = None, None
            if time != '모름':
                am = re.search(r'(오전|오후)', time)
                hm = re.search(r'(\d+)시', time)
                if am and hm: ampm = am.group(1); hour = int(hm.group(1))
            sf, ss = calc_saju(yr, mo, dy, hour, ampm)
            BASE_CACHE[base_key] = {'saju': sf, 'saju_str': ss, 'preview': ''}
        cached = BASE_CACHE[base_key]
        if detail_key not in DETAIL_CACHE:
            prompt = (
                      f"당신은 영험한 명리학자 유도령이오. 위엄 있는 도사님 말투(~하오, ~이니라, ~할 것이오)를 한결같이 쓰시오.\n"
                      f"이모지, 별표(**), 밑줄(__), 특수기호 일절 사용하지 마시오.\n"
                      f"숫자 목록이나 항목 기호 사용하지 마시오. 모든 내용은 자연스러운 문장으로 이어 서술하시오.\n"
                      f"인공지능, 데이터, AI, 알고리즘 같은 단어는 절대 쓰지 마시오.\n"
                      f"한자를 쓸 때는 반드시 괄호 안에 한글 독음을 병기하시오. 예) 庚金(경금), 丙午(병오)\n"
                      f"항목 구분이 필요하면 빈 줄로만 구분하고 제목 앞에 어떤 기호도 붙이지 마시오.\n\n"
                      f"{name}님 정보: {name} / {gender} / {birth} / {time}\n"
                      f"사주팔자: {cached['saju_str']}\n\n"
                      + FULL_ANALYSIS_PROMPT)
            DETAIL_CACHE[detail_key] = attach_nim(call_gemini(prompt, temperature=0.5), [name])
        return jsonify({'detail': DETAIL_CACHE[detail_key]})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/clear_cache', methods=['POST'])
def clear_cache():
    BASE_CACHE.clear()
    DETAIL_CACHE.clear()
    GUNGHAP_CACHE.clear()
    SINNYEON_CACHE.clear()
    return jsonify({"ok": True})


# ─── 짝궁합 라우트 ───────────────────────────────────────────────
def parse_birth_params2(data, prefix):
    """짝궁합용 - prefix='1' or '2'"""
    birth = data.get(f'birth{prefix}', '')
    time  = data.get(f'time{prefix}', '모름')
    lunar = data.get(f'lunar{prefix}', False)
    leap  = data.get(f'leap{prefix}', False)

    if birth and lunar:
        try:
            y, m, d = [int(x) for x in birth.split('-')]
            sy, sm, sd = lunar_to_solar(y, m, d, leap)
            birth = f"{sy}-{sm:02d}-{sd:02d}"
        except:
            pass
    return birth, time

# ─── 짝궁합 ────────────────────────────────────────────────────────

GUNGHAP_CACHE = {}  # 궁합 캐시

def make_gunghap_key(g1, b1, t1, g2, b2, t2):
    return hashlib.md5(f"{g1}|{b1}|{t1}|{g2}|{b2}|{t2}".encode()).hexdigest()

@app.route('/gunghap')
def gunghap_page():
    return render_template('gunghap.html')

@app.route('/gunghap_preview', methods=['POST'])
def gunghap_preview():
    """두 사람 사주 계산 + 무료 궁합 맛보기"""
    data = request.json
    n1, g1 = data['name1'], data['gender1']
    n2, g2 = data['name2'], data['gender2']
    b1, t1 = parse_birth_params2(data, '1')
    b2, t2 = parse_birth_params2(data, '2')

    try:
        # 두 사람 사주 계산
        def parse_birth(birth, time):
            y, m, d = [int(x) for x in birth.split('-')]
            hour, ampm = None, None
            if time != '모름':
                am_match = re.search(r'(오전|오후)', time)
                h_match  = re.search(r'(\d+)시', time)
                if am_match and h_match:
                    ampm = am_match.group(1)
                    hour = int(h_match.group(1))
            return calc_saju(y, m, d, hour, ampm)

        saju1_flat, saju1_str = parse_birth(b1, t1)
        saju2_flat, saju2_str = parse_birth(b2, t2)

        # 오행 상생/상극 판단
        il1 = saju1_flat.get('일주천간', {}).get('oheng', '')
        il2 = saju2_flat.get('일주천간', {}).get('oheng', '')

        SANGSAENG = [('목','화'),('화','토'),('토','금'),('금','수'),('수','목')]
        SANGGEUK  = [('목','토'),('토','수'),('수','화'),('화','금'),('금','목')]

        if (il1, il2) in SANGSAENG or (il2, il1) in SANGSAENG:
            relation = '상생(相生) — 서로를 살리는 기운'
        elif (il1, il2) in SANGGEUK or (il2, il1) in SANGGEUK:
            relation = '상극(相克) — 긴장과 자극의 기운'
        else:
            relation = '비화(比和) — 같은 기운끼리의 만남'

        # 맛보기 프롬프트
        prompt = f"""당신은 사주명리학의 대가 유도령이오. 위엄 있는 도사님 말투를 쓰시오.
인공지능, 데이터, AI 같은 단어는 절대 금지하오. 이모지나 특수기호는 쓰지 마시오.

{n1}님({il1}) / {n2}님({il2}) — 일간 관계: {relation}
{n1}님 사주: {saju1_str}
{n2}님 사주: {saju2_str}

두 사람의 짝궁합 핵심을 딱 2~3문장으로만 서술하시오.
오행 관계가 실제 관계에 어떻게 나타나는지 명리학 용어로 구체적으로 쓰시오.
"""
        preview = trim_preview(attach_nim(call_gemini(prompt, temperature=0.6), [n1, n2]))

        return jsonify({
            'saju1': saju1_flat,
            'saju2': saju2_flat,
            'saju1_str': saju1_str,
            'saju2_str': saju2_str,
            'il1': il1, 'il2': il2,
            'relation': relation,
            'preview': preview
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/gunghap_detail', methods=['POST'])
def gunghap_detail():
    """결제 후 상세 궁합 분석"""
    data = request.json
    n1, g1 = data['name1'], data['gender1']
    n2, g2 = data['name2'], data['gender2']
    b1, t1 = parse_birth_params2(data, '1')
    b2, t2 = parse_birth_params2(data, '2')
    try:
        def _calc(birth, time):
            y, m, d = [int(x) for x in birth.split('-')]
            hour, ampm = None, None
            if time != '모름':
                am = re.search(r'(오전|오후)', time)
                hm = re.search(r'(\d+)시', time)
                if am and hm: ampm = am.group(1); hour = int(hm.group(1))
            return calc_saju(y, m, d, hour, ampm)
        sf1, ss1 = _calc(b1, t1)
        sf2, ss2 = _calc(b2, t2)
        il1 = (sf1.get('일주천간') or {}).get('oheng', '')
        il2 = (sf2.get('일주천간') or {}).get('oheng', '')
        SANGSAENG = [('목','화'),('화','토'),('토','금'),('금','수'),('수','목')]
        SANGGEUK  = [('목','토'),('토','수'),('수','화'),('화','금'),('금','목')]
        if   (il1,il2) in SANGSAENG or (il2,il1) in SANGSAENG: rel = '상생(相生) 서로를 살리는 기운'
        elif (il1,il2) in SANGGEUK  or (il2,il1) in SANGGEUK:  rel = '상극(相克) 긴장과 자극의 기운'
        else:                                                     rel = '비화(比和) 같은 기운끼리의 만남'
        gkey = make_gunghap_key(g1, b1, t1, g2, b2, t2)
        if gkey not in GUNGHAP_CACHE:
            prompt = (
                      f"당신은 영험한 명리학자 유도령이오. 위엄 있는 도사님 말투(~하오, ~이니라, ~할 것이오)를 한결같이 쓰시오.\n"
                      f"이모지, 별표(**), 밑줄(__), 특수기호 일절 사용하지 마시오.\n"
                      f"숫자 목록이나 항목 기호 사용하지 마시오. 모든 내용은 자연스러운 문장으로 이어 서술하시오.\n"
                      f"인공지능, 데이터, AI, 알고리즘 같은 단어는 절대 쓰지 마시오.\n"
                      f"한자를 쓸 때는 반드시 괄호 안에 한글 독음을 병기하시오. 예) 庚金(경금), 丙午(병오)\n"
                      f"항목 구분이 필요하면 빈 줄로만 구분하고 제목 앞에 어떤 기호도 붙이지 마시오.\n\n"
                      f"[{n1}님] {g1} / {b1} / {t1}\n사주: {ss1} / 일간: {il1}\n\n"
                      f"[{n2}님] {g2} / {b2} / {t2}\n사주: {ss2} / 일간: {il2}\n\n"
                      f"두 사람 일간 관계: {rel}\n\n"
                      + GUNG_PROMPT)
            GUNGHAP_CACHE[gkey] = attach_nim(call_gemini(prompt, temperature=0.5), [n1, n2])
        return jsonify({'detail': GUNGHAP_CACHE[gkey], 'saju1': sf1, 'saju2': sf2})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─── 신년운세 라우트 ──────────────────────────────────────────────
def make_sinnyeon_key(gender, birth, time):
    return hashlib.md5(f"sinnyeon|{gender}|{birth}|{time}".encode()).hexdigest()

@app.route('/sinnyeon')
def sinnyeon_page():
    return render_template('sinnyeon.html')

@app.route('/sinnyeon_preview', methods=['POST'])
def sinnyeon_preview():
    """신년운세 무료 맛보기 - 사주 계산 + 2026년 총운 한 문단"""
    try:
        data = request.json
        gender, name = data.get('gender',''), data.get('name','')
        birth, time = parse_birth_params(data)
        base_key = make_base_key(gender, birth, time)
        parts = birth.split('-')
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        hour, ampm = None, None
        if time != '모름':
            am_match = re.search(r'(오전|오후)', time)
            h_match  = re.search(r'(\d+)시', time)
            if am_match and h_match:
                ampm = am_match.group(1)
                hour = int(h_match.group(1))

        saju_flat, saju_str = calc_saju(year, month, day, hour, ampm)

        if base_key not in BASE_CACHE:
            BASE_CACHE[base_key] = {'saju': saju_flat, 'saju_str': saju_str, 'preview': ''}

        ilgan = saju_flat.get('일주천간', {})

        prompt = f"""당신은 사주명리학의 대가 유도령이오. 위엄 있는 도사님 말투를 쓰시오.
인공지능, 데이터, AI 같은 단어는 절대 금지하오. 이모지나 특수기호는 쓰지 마시오.
의뢰인을 부를 때는 반드시 이름 뒤에 님을 붙이시오. 예) 홍길동님.

{name}님 사주: {gender} / {birth} / {saju_str}
일간: {ilgan.get('hanja','?')}({ilgan.get('oheng','?')})

{name}님의 2026년 병오년 신년운세 핵심을 딱 2~3문장으로만 서술하시오.
병오년의 기운이 이 사주에 어떻게 작용하는지 명리학 용어로 구체적으로 쓰시오.
"""
        preview = trim_preview(call_gemini(prompt, temperature=0.6))

        return jsonify({'saju': saju_flat, 'preview': preview})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

@app.route('/sinnyeon_detail', methods=['POST'])
def sinnyeon_detail():
    """신년운세 유료 상세"""
    data = request.json
    gender, name = data['gender'], data['name']
    birth, time = parse_birth_params(data)
    skey     = make_sinnyeon_key(gender, birth, time)
    base_key = make_base_key(gender, birth, time)
    try:
        if base_key not in BASE_CACHE:
            parts = birth.split('-')
            yr, mo, dy = int(parts[0]), int(parts[1]), int(parts[2])
            hour, ampm = None, None
            if time != '모름':
                am = re.search(r'(오전|오후)', time)
                hm = re.search(r'(\d+)시', time)
                if am and hm: ampm = am.group(1); hour = int(hm.group(1))
            sf, ss = calc_saju(yr, mo, dy, hour, ampm)
            BASE_CACHE[base_key] = {'saju': sf, 'saju_str': ss, 'preview': ''}
        saju_str = BASE_CACHE[base_key]['saju_str']
        if skey not in SINNYEON_CACHE:
            prompt = (
                      f"당신은 영험한 명리학자 유도령이오. 위엄 있는 도사님 말투(~하오, ~이니라, ~할 것이오)를 한결같이 쓰시오.\n"
                      f"이모지, 별표(**), 밑줄(__), 특수기호 일절 사용하지 마시오.\n"
                      f"숫자 목록이나 항목 기호 사용하지 마시오. 모든 내용은 자연스러운 문장으로 이어 서술하시오.\n"
                      f"인공지능, 데이터, AI, 알고리즘 같은 단어는 절대 쓰지 마시오.\n"
                      f"한자를 쓸 때는 반드시 괄호 안에 한글 독음을 병기하시오. 예) 庚金(경금), 丙午(병오)\n"
                      f"항목 구분이 필요하면 빈 줄로만 구분하고 제목 앞에 어떤 기호도 붙이지 마시오.\n\n"
                      f"{name}님 정보: {name} / {gender} / {birth} / {time}\n"
                      f"사주팔자: {saju_str}\n\n"
                      + SINN_PROMPT)
            SINNYEON_CACHE[skey] = attach_nim(call_gemini(prompt, temperature=0.5), [name])
        return jsonify({'detail': SINNYEON_CACHE[skey]})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
