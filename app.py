import requests
import traceback
import os
import hashlib
import re
import sqlite3
from datetime import date
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
API_KEY = os.environ.get("GEMINI_API_KEY")

# ─── 직원 관리 DB ─────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), 'employees.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL,
                dept       TEXT    NOT NULL,
                position   TEXT    NOT NULL,
                hire_date  TEXT    NOT NULL,
                phone      TEXT,
                email      TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        ''')
        conn.commit()

init_db()

# ─── 만세력 상수 ──────────────────────────────────────────────────
CHEONGAN  = ['갑','을','병','정','무','기','경','신','임','계']
JIJI      = ['자','축','인','묘','진','사','오','미','신','유','술','해']
CG_HANJA  = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
JJ_HANJA  = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']
OHENG_CG  = ['목','목','화','화','토','토','금','금','수','수']
OHENG_JJ  = ['수','토','목','목','토','화','화','토','금','금','토','수']

OHENG_COLOR  = {'목':'#7acc50','화':'#ff6640','토':'#ddaa20','금':'#99aaee','수':'#44aaee'}
OHENG_BG     = {'목':'rgba(60,120,20,0.25)','화':'rgba(150,30,5,0.25)',
                '토':'rgba(120,80,0,0.25)', '금':'rgba(40,40,120,0.25)','수':'rgba(5,40,100,0.25)'}
OHENG_BORDER = {'목':'rgba(80,160,40,0.4)','화':'rgba(200,60,20,0.4)',
                '토':'rgba(180,140,0,0.4)','금':'rgba(100,120,200,0.4)','수':'rgba(20,100,180,0.4)'}


# ─── 만세력 계산 함수 ─────────────────────────────────────────────
def get_month_jiji(month, day):
    """절기 기준 월지지 - 올바른 계산
    1월=축(1), 2월=인(2), 3월=묘(3), 4월=진(4), 5월=사(5), 6월=오(6)
    7월=미(7), 8월=신(8), 9월=유(9), 10월=술(10), 11월=해(11), 12월=자(0)
    """
    starts = [6, 4, 6, 5, 6, 6, 7, 8, 8, 8, 7, 7]
    if day >= starts[month - 1]:
        m = month
    else:
        m = month - 1 if month > 1 else 12
    return m % 12  # 12월→0(자), 1~11월→그대로

def calc_saju(year, month, day, hour=None, ampm=None):
    """실제 만세력으로 사주팔자 계산. (saju_flat, saju_str) 반환"""
    import datetime

    # ── 시간 → 24시간제 변환 ──
    h24 = None
    if hour is not None:
        h24 = hour
        if ampm == '오후' and hour != 12:
            h24 = hour + 12
        elif ampm == '오전' and hour == 12:
            h24 = 0

    # ── 년주 계산 ──
    # 입춘(2월 4일) 기준으로 연주 결정
    if (month == 1) or (month == 2 and day < 4):
        year_gan_idx = (year - 1 - 4) % 10
        year_ji_idx  = (year - 1 - 4) % 12
    else:
        year_gan_idx = (year - 4) % 10
        year_ji_idx  = (year - 4) % 12

    # ── 월주 계산 ──
    month_ji_idx = get_month_jiji(month, day)
    # 월간: 년간 기준 오행 순환
    month_gan_idx = ((year_gan_idx % 5) * 2 + month_ji_idx) % 10

    # ── 일주 계산 ── (기준: 2000-01-07 갑자일 = 간지 0)
    base_date = datetime.date(2000, 1, 7)
    target_date = datetime.date(year, month, day)
    diff = (target_date - base_date).days
    day_gan_idx = diff % 10
    day_ji_idx  = diff % 12

    # ── 시주 계산 ──
    if h24 is None:
        shi_gan_idx = None
        shi_ji_idx  = None
    else:
        # 시지: 자시(23~1)=0, 축시(1~3)=1, ...
        shi_ji_idx = ((h24 + 1) // 2) % 12
        shi_gan_idx = ((day_gan_idx % 5) * 2 + shi_ji_idx) % 10

    def make_cell(gan_idx, ji_idx):
        if gan_idx is None:
            return None
        cg = CHEONGAN[gan_idx]; cg_h = CG_HANJA[gan_idx]; cg_o = OHENG_CG[gan_idx]
        jj = JIJI[ji_idx];     jj_h = JJ_HANJA[ji_idx];  jj_o = OHENG_JJ[ji_idx]
        return {
            'gan': {'hanja': cg_h, 'hangul': cg, 'oheng': cg_o,
                    'color': OHENG_COLOR[cg_o], 'bg': OHENG_BG[cg_o], 'border': OHENG_BORDER[cg_o]},
            'ji':  {'hanja': jj_h, 'hangul': jj, 'oheng': jj_o,
                    'color': OHENG_COLOR[jj_o], 'bg': OHENG_BG[jj_o], 'border': OHENG_BORDER[jj_o]},
        }

    year_cell  = make_cell(year_gan_idx,  year_ji_idx)
    month_cell = make_cell(month_gan_idx, month_ji_idx)
    day_cell   = make_cell(day_gan_idx,   day_ji_idx)
    shi_cell   = make_cell(shi_gan_idx,   shi_ji_idx)

    # flat 딕셔너리 (기존 코드 호환)
    def flat_cell(cell, prefix):
        if not cell: return {f'{prefix}천간': None, f'{prefix}지지': None}
        return {
            f'{prefix}천간': {'hanja': cell['gan']['hanja'], 'hangul': cell['gan']['hangul'],
                               'oheng': cell['gan']['oheng'], 'color': cell['gan']['color'],
                               'bg': cell['gan']['bg'], 'border': cell['gan']['border']},
            f'{prefix}지지': {'hanja': cell['ji']['hanja'],  'hangul': cell['ji']['hangul'],
                               'oheng': cell['ji']['oheng'],  'color': cell['ji']['color'],
                               'bg': cell['ji']['bg'],  'border': cell['ji']['border']},
        }

    saju_flat = {}
    saju_flat.update(flat_cell(shi_cell,  '시주'))
    saju_flat.update(flat_cell(day_cell,  '일주'))
    saju_flat.update(flat_cell(month_cell,'월주'))
    saju_flat.update(flat_cell(year_cell, '년주'))

    # 오행 강약 계산
    oheng_count = {'목':0,'화':0,'토':0,'금':0,'수':0}
    for key, val in saju_flat.items():
        if val and 'oheng' in val:
            oheng_count[val['oheng']] = oheng_count.get(val['oheng'], 0) + 1
    sorted_oh = sorted(oheng_count.items(), key=lambda x: -x[1])
    strong = [o for o,c in sorted_oh if c == sorted_oh[0][1]]
    weak   = [o for o,c in sorted_oh if c == sorted_oh[-1][1]]
    saju_flat['강한기운'] = '·'.join(strong)
    saju_flat['약한기운'] = '·'.join(weak)

    # 문자열 표현
    def cell_str(cell):
        if not cell: return '時不明'
        return f"{cell['gan']['hangul']}{cell['ji']['hangul']}({cell['gan']['hanja']}{cell['ji']['hanja']})"

    saju_str = f"년주:{cell_str(year_cell)} 월주:{cell_str(month_cell)} 일주:{cell_str(day_cell)} 시주:{cell_str(shi_cell)}"

    return saju_flat, saju_str


# ─── 음력→양력 변환 ────────────────────────────────────────────────────

def lunar_to_solar(year, month, day, is_leap=False):
    """음력 날짜를 양력으로 변환."""
    try:
        from korean_lunar_calendar import KoreanLunarCalendar
        cal = KoreanLunarCalendar()
        cal.setLunarDate(year, month, day, is_leap)
        solar = cal.SolarIsoFormat()
        parts = solar.split("-")
        return int(parts[0]), int(parts[1]), int(parts[2])
    except Exception:
        pass
    import datetime
    offsets = [0, 20, 20, 20, 21, 21, 22, 23, 24, 24, 25, 25, 26]
    offset = offsets[month] if 1 <= month <= 12 else 20
    try:
        lunar_date = datetime.date(year, month, day)
        solar_date = lunar_date + datetime.timedelta(days=offset)
        return solar_date.year, solar_date.month, solar_date.day
    except:
        return year, month, day


# ─── 실제 만세력 계산 ────────────────────────────────────────────
CHEONGAN  = ['갑','을','병','정','무','기','경','신','임','계']
JIJI      = ['자','축','인','묘','진','사','오','미','신','유','술','해']
CG_HANJA  = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
JJ_HANJA  = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']
OHENG_CG  = ['목','목','화','화','토','토','금','금','수','수']
OHENG_JJ  = ['수','토','목','목','토','화','화','토','금','금','토','수']

OHENG_COLOR  = {'목':'#7acc50','화':'#ff6640','토':'#ddaa20','금':'#99aaee','수':'#44aaee'}
OHENG_BG     = {'목':'rgba(60,120,20,0.25)','화':'rgba(150,30,5,0.25)',
                '토':'rgba(120,80,0,0.25)', '금':'rgba(40,40,120,0.25)','수':'rgba(5,40,100,0.25)'}
OHENG_BORDER = {'목':'rgba(80,160,40,0.4)','화':'rgba(200,60,20,0.4)',
                '토':'rgba(180,140,0,0.4)','금':'rgba(100,120,200,0.4)','수':'rgba(20,100,180,0.4)'}


# ─── 헬퍼 함수 ────────────────────────────────────────────────────
def make_base_key(gender, birth, time):
    return hashlib.md5(f"{gender}|{birth}|{time}".encode()).hexdigest()

def make_detail_key(gender, birth, time):
    return hashlib.md5(f"{gender}|{birth}|{time}|full".encode()).hexdigest()

def call_gemini(prompt, temperature=0.3):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "topP": 0.9, "topK": 40}
    }
    response = requests.post(url, json=payload, timeout=90)
    res = response.json()
    if 'candidates' not in res:
        raise Exception(res.get('error', {}).get('message', '오류'))
    text = res['candidates'][0]['content']['parts'][0]['text']
    # 마크다운 기호 강제 제거
    import re as _re
    text = _re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)  # **굵게**, *기울임*
    text = _re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)     # __밑줄__
    text = _re.sub(r'^#{1,6}\s+', '', text, flags=_re.MULTILINE)  # ## 헤더
    text = _re.sub(r'^[-*+]\s+', '', text, flags=_re.MULTILINE)   # - 목록
    text = _re.sub(r'^\d+\.\s+', '', text, flags=_re.MULTILINE)   # 1. 목록
    text = _re.sub(r'`([^`]+)`', r'\1', text)                     # `코드`
    text = _re.sub(r'-{3,}|={3,}', '', text)                      # 구분선
    return text.strip()

def attach_nim(text, names):
    """이름 단독 호칭 → 이름님 으로 강제 교체"""
    import re as _re
    for name in names:
        if not name:
            continue
        # 이름 뒤에 님이 없는 경우만 교체 (이름님은 그대로)
        text = _re.sub(r'(?<!' + '님)' + _re.escape(name) + r'(?!님)(?=[은는이가을를의도와과]|\s|$)', name + '님', text)
    return text

def trim_preview(text, max_chars=120):
    """맛보기 텍스트 - 120자 내외 문장 끝에서 자르고 ... 붙임"""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for ending in ['하오', '이오', '이니라', '것이오', '하리라', '이라', '다.', '요.', '오.', '다', '요', '오']:
        idx = cut.rfind(ending)
        if idx > 30:
            return cut[:idx + len(ending)] + '...'
    sp = cut.rfind(' ')
    if sp > 30:
        return cut[:sp] + '...'
    return cut + '...'

def parse_birth_params(data):
    """요청 데이터에서 birth, time 파싱. 음력이면 양력으로 변환."""
    birth = data.get('birth', '')
    time  = data.get('time', '모름')
    lunar = data.get('lunar', False)
    leap  = data.get('leap', False)

    if birth and lunar:
        try:
            y, m, d = [int(x) for x in birth.split('-')]
            sy, sm, sd = lunar_to_solar(y, m, d, leap)
            birth = f"{sy}-{sm:02d}-{sd:02d}"
        except:
            pass
    return birth, time


# ─── 프롬프트 ─────────────────────────────────────────────────────
FULL_ANALYSIS_PROMPT = """
당신은 수십 년 경력의 명리학자 유도령이오. 지금부터 의뢰인의 사주팔자 원국을 감정서 형식으로 풀어주시오.
의뢰인을 부를 때는 반드시 이름 뒤에 님을 붙여 호칭하시오. 예) 홍길동님, 김영희님. 절대 이름만 단독으로 쓰지 마시오.
이 감정서는 타고난 사주 원국 분석에 집중하시오. 월별 운세나 신년운세 내용은 절대 포함하지 마시오.
항목 제목은 [ ] 안에 표시하고, 본문은 자연스러운 문장으로 이어 쓰시오.
별표, 이모지, 구분선, 숫자 목록 등 일체의 기호는 절대 쓰지 마시오.
한자를 쓸 때는 반드시 괄호 안에 한글 독음을 병기하시오.
명리학 용어를 처음 등장할 때는 반드시 쉬운 말로 풀어 설명하시오. 예) 일간(내 사주의 중심이 되는 글자), 용신(내 사주에 가장 도움이 되는 기운), 관성(직업·사회적 지위와 관련된 기운) 처럼 괄호 안에 일반인도 바로 이해할 수 있게 설명하시오.
각 항목의 내용이 다른 항목과 겹치지 않도록 하시오. 같은 내용을 반복하지 마시오.

[사주 원국 해석]

일간(내 사주의 중심 글자)의 오행과 음양을 중심으로 이 사람이 타고난 본질적 기질을 설명하시오.
년주·월주·일주·시주가 서로 어떻게 작용하는지, 천간과 지지의 합·충·형·파 관계를 짚어주시오.
오행의 과다와 결핍이 삶 전체에 어떤 구체적인 패턴으로 드러나는지 서술하시오.
용신(내 사주에 가장 도움이 되는 기운)과 기신(내 사주를 방해하는 기운)이 무엇인지, 그것이 이 사람의 삶에 어떻게 작용해왔는지 설명하시오.

[타고난 성격과 내면]

겉으로 드러나는 성격과 혼자 있을 때의 본 모습이 어떻게 다른지 사주 근거와 함께 서술하시오.
이 사람이 평생 반복하는 심리 패턴, 강점, 그리고 스스로도 모르는 약점을 짚어주시오.
인간관계에서 이 사람이 본능적으로 끌리는 유형과 갈등을 일으키는 유형을 설명하시오.

[연애와 결혼운]

이 사주에서 배우자성(배우자와 인연을 맺게 해주는 기운)이 어디에 어떻게 자리하고 있는지 구체적으로 설명하시오.
평생 인연이 들어오는 나이대와 잘 맞는 상대의 오행·일간을 알려주시오.
결혼 후 가정운의 흐름, 부부 관계의 특징과 주의점을 서술하시오.

[직업·적성·커리어운]

관성(직업·사회적 지위와 관련된 기운)과 식상(재능·표현력과 관련된 기운)의 배치로 본 타고난 직업 적성과 능력을 설명하시오.
평생 가장 빛날 수 있는 분야와 피해야 할 분야를 구체적으로 짚어주시오.
직장 생활과 사업 중 어느 쪽이 맞는지, 평생 커리어의 큰 흐름을 서술하시오.

[재물운과 금전 흐름]

정재(꾸준히 벌어들이는 돈)와 편재(한번에 크게 들어오는 돈)의 비율과 위치로 본 이 사람과 돈의 근본적인 관계를 설명하시오.
재물이 쌓이는 방식, 돈을 버는 패턴, 새어나가는 구멍이 어디인지 서술하시오.
평생 재물운의 큰 흐름과 노년의 경제적 안정 여부를 서술하시오.

[건강과 체질]

오행의 불균형이 신체 어느 기관에 영향을 미치는지 오장육부와 연결하여 설명하시오.
평생 조심해야 할 지병이나 체질적 약점, 건강 관리 방향을 짚어주시오.

[올해 2026년 한 줄 총평]

타고난 사주 원국을 바탕으로, 2026년 병오년이 이 사람에게 어떤 해인지 딱 두세 문장으로만 짚어주시오.
월별 분석이나 영역별 세부 운세는 쓰지 마시오. 그것은 신년운세에서 다루는 내용이오.

최소 60줄 이상, 읽는 사람이 자신의 이야기라고 느낄 만큼 구체적이고 개인화된 감정서를 작성하시오.
각 항목은 서로 내용이 겹치지 않게 하고, 억지로 분량을 늘리지 마시오.
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

            # ── 2. 맛보기만 Gemini에게 (사주 계산값 전달) ──
            ilgan = saju_flat.get('일주천간',{})
            iljiji = saju_flat.get('일주지지',{})
            prompt = f"""당신은 사주명리학의 대가 유도령이오. 위엄 있는 도사님 말투를 쓰시오.
인공지능, 데이터, AI 같은 단어는 절대 금지하오. 이모지나 특수기호는 쓰지 마시오.
의뢰인을 부를 때는 반드시 이름 뒤에 님을 붙이시오. 예) 홍길동님.

{name}님 사주: {gender} / {birth} / {saju_str}
일주: {ilgan.get('hanja','?')}({ilgan.get('oheng','?')}) {iljiji.get('hanja','?')}({iljiji.get('oheng','?')})

{name}님의 사주를 바탕으로 타고난 기질과 올해 운세의 핵심을 딱 2~3문장으로만 서술하시오.
명리학 용어를 써서 구체적으로, 막연한 표현은 절대 금지하오.
"""
            full = call_gemini(prompt, temperature=0.6)
            preview = full.strip()
            if '[맛보기]' in preview:
                preview = preview.split('[맛보기]')[-1].strip()
            preview = trim_preview(preview)

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


# ─── 직원 관리 라우트 ─────────────────────────────────────────────
@app.route('/employees')
def employees_page():
    return render_template('employees.html')

@app.route('/api/employees', methods=['GET'])
def list_employees():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM employees ORDER BY id DESC').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/employees', methods=['POST'])
def create_employee():
    data = request.json
    name      = data.get('name', '').strip()
    dept      = data.get('dept', '').strip()
    position  = data.get('position', '').strip()
    hire_date = data.get('hire_date', '').strip()
    phone     = data.get('phone', '').strip()
    email     = data.get('email', '').strip()
    if not name or not dept or not position or not hire_date:
        return jsonify({'error': '이름, 부서, 직급, 입사일은 필수입니다.'}), 400
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO employees (name, dept, position, hire_date, phone, email) VALUES (?,?,?,?,?,?)',
            (name, dept, position, hire_date, phone, email)
        )
        conn.commit()
        row = conn.execute('SELECT * FROM employees WHERE id=?', (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201

@app.route('/api/employees/<int:emp_id>', methods=['PUT'])
def update_employee(emp_id):
    data = request.json
    name      = data.get('name', '').strip()
    dept      = data.get('dept', '').strip()
    position  = data.get('position', '').strip()
    hire_date = data.get('hire_date', '').strip()
    phone     = data.get('phone', '').strip()
    email     = data.get('email', '').strip()
    if not name or not dept or not position or not hire_date:
        return jsonify({'error': '이름, 부서, 직급, 입사일은 필수입니다.'}), 400
    with get_db() as conn:
        conn.execute(
            'UPDATE employees SET name=?, dept=?, position=?, hire_date=?, phone=?, email=? WHERE id=?',
            (name, dept, position, hire_date, phone, email, emp_id)
        )
        conn.commit()
        row = conn.execute('SELECT * FROM employees WHERE id=?', (emp_id,)).fetchone()
    if row is None:
        return jsonify({'error': '직원을 찾을 수 없습니다.'}), 404
    return jsonify(dict(row))

@app.route('/api/employees/<int:emp_id>', methods=['DELETE'])
def delete_employee(emp_id):
    with get_db() as conn:
        conn.execute('DELETE FROM employees WHERE id=?', (emp_id,))
        conn.commit()
    return jsonify({'ok': True})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
