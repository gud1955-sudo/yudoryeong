import os, re, hashlib, traceback
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types
from flask import Flask, render_template, request, jsonify, redirect
from saju_logic import calc_saju, lunar_to_solar

app = Flask(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

SYSTEM_MSG = (
    "당신은 수십 년 경력의 명리학자 유도령이오. "
    "위엄 있는 도사님 말투(~하오, ~이니라, ~할 것이오)를 한결같이 쓰시오. "
    "인공지능, 데이터, AI 같은 단어는 절대 금지하오. "
    "이모지, 샵(#), 별표(**), 특수기호는 절대 쓰지 마시오. "
    "의뢰인을 부를 때는 반드시 이름 뒤에 님을 붙이시오. "
    "반드시 한국어로만 작성하시오. 영어 단어, 영문 약어, 로마자 표기는 일절 사용하지 마시오. "
    "한자를 표기할 때는 반드시 한자(한글) 형식으로 쓰시오. 예: 庚金(경금), 甲木(갑목), 壬水(임수), 官星(관성), 食傷(식상). 한글만 단독으로 쓰거나 한자만 단독으로 쓰지 마시오. "
    "현재 연도는 2026년이오. 절대로 2025년이나 그 이전 연도를 현재·올해로 언급하지 마시오. "
    "나이를 언급할 때는 반드시 프롬프트에 제공된 만 나이와 한국 나이를 그대로 사용하시오. 임의로 나이를 계산하거나 추정하지 마시오. "
    "이미 앞에서 서술한 내용을 다른 항목에서 반복하지 마시오. 각 항목은 반드시 새로운 내용과 구체적인 근거로 채우시오."
)

def clean_output(text):
    import re
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    return text

def call_gemini(prompt, temperature=0.6):
    import time
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_MSG,
                    temperature=temperature,
                )
            )
            return clean_output(response.text)
        except Exception:
            if attempt == 0:
                time.sleep(2)
            else:
                raise

def attach_nim(text, names):
    for name in names:
        text = re.sub(rf'\b{re.escape(name)}(?!님)', f'{name}님', text)
    return text

def trim_preview(text, max_sentences=3):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return ' '.join(sentences[:max_sentences])

def parse_birth_params(data):
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

def make_key(*args):
    return hashlib.md5('|'.join(str(a) for a in args).encode()).hexdigest()

def calc_age(birth_str):
    """birth_str='YYYY-MM-DD' → (만나이, 한국나이) 반환"""
    import datetime
    try:
        parts = birth_str.split('-')
        by, bm, bd = int(parts[0]), int(parts[1]), int(parts[2])
        today = datetime.date.today()
        man_age = today.year - by - (1 if (today.month, today.day) < (bm, bd) else 0)
        korean_age = today.year - by + 1
        return man_age, korean_age
    except Exception:
        return None, None

def parse_time(time_str):
    hour, ampm = None, None
    if time_str and time_str != '모름':
        am_match = re.search(r'(오전|오후)', time_str)
        h_match  = re.search(r'(\d+)시', time_str)
        if am_match and h_match:
            ampm = am_match.group(1)
            hour = int(h_match.group(1))
    return hour, ampm

DETAIL_BASE = (
    "당신은 영험한 명리학자 유도령이오. 위엄 있는 도사님 말투(~하오, ~이니라, ~할 것이오)를 한결같이 쓰시오.\n"
    "이모지, 별표(**), 밑줄(__), 샵(#), 특수기호 일절 사용하지 마시오.\n"
    "인공지능, 데이터, AI, 알고리즘 같은 단어는 절대 쓰지 마시오.\n"
    "한자를 표기할 때는 반드시 한자(한글) 형식으로 쓰시오. 예: 庚金(경금), 甲木(갑목), 壬水(임수), 丙火(병화), 官星(관성), 食傷(식상), 偏財(편재), 正財(정재). 한글만 단독으로 쓰거나 한자만 단독으로 쓰지 마시오.\n"
    "제목 앞에 어떤 기호도 붙이지 마시오.\n"
    "각 대항목 제목(예: '1. 선천적 기질 및 성향')은 반드시 출력하시오. 소항목 제목은 프롬프트에 제시된 예시 단어에 구애받지 말고, 해당 문단의 내용을 가장 잘 표현하는 제목을 직접 지으시오. 제목 뒤 빈 줄을 두고 내용을 서술하시오.\n"
    "현재 연도는 2026년이오. 절대로 2025년이나 그 이전 연도를 현재·올해로 언급하지 마시오.\n"
    "나이를 언급할 때는 반드시 프롬프트에 제공된 만 나이와 한국 나이를 그대로 사용하시오. 임의로 나이를 계산하거나 추정하지 마시오.\n"
    "이 사주 풀이는 정통사주이오. 인생 전반의 타고난 운명과 대운의 큰 흐름을 중심으로 서술하시오. 특정 연도(2026년 등)에 집중하거나 올해 운세 위주로 풀지 마시오.\n"
    "의뢰인의 성별(남성·여성)을 반드시 고려하여 서술하시오. 여성의 경우 관성(官星)이 남편·배우자를 뜻하고, 남성의 경우 재성(財星)이 배우자를 뜻하는 등 성별에 따라 십신 해석을 달리하시오.\n"
    "시기를 언급할 때는 '가까운 1~2년', '30대 중반 이후', '현재 대운이 지나는 동안' 등 상대적인 표현을 쓰시오. 특정 연도나 월을 단정 짓지 마시오.\n"
    "앞 항목에서 이미 서술한 내용을 뒤 항목에서 반복하지 마시오. 동일한 오행·살·합 근거를 여러 항목에 걸쳐 중복 사용하지 마시오. 각 항목은 독립적이고 새로운 내용으로 채우시오.\n"
    "반드시 한국어로만 작성하시오. 영어 단어, 영문 약어, 로마자 표기는 일절 사용하지 마시오.\n\n"
)

# ─── 나이 구분 ──────────────────────────────────────────────────────
def age_group(man_age):
    a = man_age or 35
    if a < 27:  return 'youth'   # 청년기
    if a < 45:  return 'prime'   # 활동기
    if a < 62:  return 'middle'  # 중년기
    return 'elder'               # 노년기

# ─── 프롬프트 ────────────────────────────────────────────────────────

def make_full_prompt(man_age):
    ag = age_group(man_age)

    # 공통 섹션 1 — 기질
    s1 = """1. 선천적 기질 및 성향

나의 핵심 오행: 일간을 중심으로 타고난 본연의 기질과 성질을 서술하시오.
심리 분석: 십신(十神)을 통한 성격 장단점과 무의식적으로 반복하는 행동 패턴을 짚어주시오.
사회적 페르소나: 타인에게 보여지는 겉모습과 실제 내면의 차이를 사주 근거와 함께 설명하시오."""

    # 섹션 2 — 재물 (나이별)
    if ag == 'youth':
        s2 = """2. 재물 및 경제 첫걸음

재물 그릇: 이 사주의 타고난 자산 규모와 돈을 대하는 방식을 서술하시오.
사회 초년 재물 전략: 첫 경제 활동에서 재물 기반을 다지는 방향과 주의할 지출 습관을 안내하시오."""
    elif ag == 'prime':
        s2 = """2. 재물 및 경제운

재물 그릇의 크기: 정재(正財)와 편재(偏財)의 배치로 본 자산 규모와 돈을 모으는 방식을 서술하시오.
투자 성향: 공격적 투자와 안정적 저축 중 이 사주에 맞는 방식과 그 이유를 설명하시오.
재물 흐름: 가까운 시기 재물이 강해지는 때와 지출을 단속해야 할 때를 상반기·하반기 흐름으로 서술하시오."""
    elif ag == 'middle':
        s2 = """2. 재물 운용 및 노후 준비

재물 운용: 현재 나이대에 맞는 자산 관리 방향과 타고난 재물 그릇을 서술하시오.
노후 준비: 이 사주가 재물을 안정적으로 지키기 위해 유의할 점을 짚어주시오.
재물 흐름: 올 한 해 재물이 강해지는 시기와 조심해야 할 시기를 상·하반기로 서술하시오."""
    else:
        s2 = """2. 노후 재물 및 경제적 평안

노후 재물: 이 사주가 노후에 재물을 지키고 운용하기에 좋은 방향을 서술하시오.
경제적 안정: 현재 나이대에 재물을 평안히 유지하기 위한 생활 방침을 안내하시오."""

    # 섹션 3 — 직업/커리어 (나이별)
    if ag == 'youth':
        s3 = """3. 학업 및 진로

천직과 적성: 관성(官星)과 식상(食傷)의 배치로 본 적합한 학업 분야와 직업 방향을 추천하시오.
사회 첫걸음: 20대에 진로를 설정하기 좋은 시기와 피해야 할 선택을 안내하시오."""
    elif ag == 'prime':
        s3 = """3. 직업 및 커리어

천직과 직업군: 관성과 식상의 배치로 본 유리한 산업군과 직업 유형을 추천하시오.
직장 내 처세: 상사·동료와의 관계 패턴 및 승진운의 흐름을 서술하시오.
변화 타이밍: 이직·창업에 기운이 좋은 시기와 피해야 할 시기를 짚어주시오."""
    elif ag == 'middle':
        s3 = """3. 커리어 후반 및 인생 전환

커리어 전반: 현재 나이대 직업운의 흐름과 전문성을 살리는 방향을 서술하시오.
인생 2막: 은퇴 이후 또는 인생 후반부를 준비하기에 유리한 시기와 방향을 안내하시오."""
    else:
        s3 = """3. 인생 후반 및 사회적 역할

역할과 활동: 현재 나이대에 이 사주가 사회·가족 안에서 맡는 역할과 어울리는 활동을 서술하시오.
안정적 일상: 무리 없이 활동하기 좋은 분야와 일상 유지 방법을 안내하시오."""

    # 섹션 4 — 인간관계 (나이별)
    if ag == 'youth':
        s4 = """4. 애정 및 인간관계

연애 스타일: 이 사람이 끌리는 상대 유형과 실제로 잘 맞는 상대의 오행·일간 차이를 설명하시오.
인연의 시기: 이 사주에서 인연이 들어오기 좋은 흐름과 연애에서 주의할 습관을 짚어주시오.
대인관계: 또래·선후배와의 관계에서 반복하는 패턴과 개선 방법을 짚어주시오."""
    elif ag == 'prime':
        s4 = """4. 애정 및 인간관계

연애 스타일: 이 사람이 끌리는 상대 유형과 실제로 잘 맞는 상대의 차이를 사주로 설명하시오.
결혼 및 배우자운: 인연이 나타나는 시기와 배우자의 오행·일간 특징을 서술하시오.
대인관계 솔루션: 갈등이 생기기 쉬운 살이나 합의 작용과 개선 방법을 제시하시오."""
    elif ag == 'middle':
        s4 = """4. 가족 및 인간관계

부부·자녀 관계: 배우자·자녀와의 관계 흐름과 조화롭게 지내는 방법을 사주 근거로 서술하시오.
대인관계: 현재 나이대에 주의해야 할 관계 패턴과 주변 사람들과의 소통 방법을 짚어주시오."""
    else:
        s4 = """4. 가족 및 노년의 인간관계

자녀·손자 관계: 이 사주에서 자녀·손자와의 인연이 어떻게 흐르는지 서술하시오.
노년의 동반자: 함께하면 좋은 사람의 기운과 피해야 할 관계 유형을 짚어주시오."""

    # 섹션 5 — 건강 (나이별 비중 증가)
    if ag in ('youth', 'prime'):
        s5 = """5. 건강 및 라이프스타일

취약한 신체 부위: 오행의 과다·결핍에 따라 주의해야 할 신체 부위와 질환을 설명하시오.
맞춤형 개운법: 부족한 기운을 채워주는 행운의 색상·방향·음식을 안내하시오.
멘탈 관리: 스트레스에 취약한 시기와 마음을 다스리는 방법을 서술하시오."""
    else:
        s5 = """5. 건강 관리 및 양생법

주요 취약 부위: 나이와 오행 과다·결핍을 함께 고려해 각별히 챙겨야 할 신체 부위를 상세히 서술하시오.
계절별 건강: 기운이 약해지기 쉬운 계절과 그 시기 몸을 지키는 방법을 안내하시오.
개운 및 양생법: 이 사주에 맞는 음식·운동·생활 습관을 구체적으로 제시하시오."""

    # 섹션 6 — 대운과 인생 주기 (연도 단정 없이)
    if ag == 'elder':
        s6 = """6. 대운과 인생 주기

대운 분석: 현재 대운의 흐름 속에서 이 사람이 인생의 어느 단계에 있는지 설명하시오.
가까운 시기의 흐름: 향후 1~3년 안팎의 운세 흐름을 '가까운 시일 내', '1~2년 이내' 등 유연한 표현으로 서술하시오. 특정 연도를 단정 짓지 마시오.
평안한 노후를 위한 길: 남은 삶을 편안하게 살아가기 위해 이 사주가 알려주는 방향을 짚어주시오."""
    else:
        s6 = """6. 대운과 인생 주기

대운 분석: 현재 대운의 흐름 속에서 이 사람이 인생의 어느 단계에 있는지 설명하시오.
앞으로의 운세 흐름: 가까운 1~3년과 5~10년 후의 큰 기운 변화를 '가까운 시일', '수년 이내', '대운이 바뀌는 무렵' 등 상대적인 표현으로 서술하시오. 특정 연도나 월을 단정 짓지 마시오.
인생의 골든타임: 중요한 결정을 내리기에 가장 길한 시기를 나이대 또는 대운 기준으로 짚어주시오."""

    closing = "\n마지막은 유도령이 이 사람의 삶 전체를 꿰뚫어 본 뒤 전하는 진심 어린 한 마디로 마무리하시오."

    return (
        "아래 6개 카테고리를 순서대로 빠짐없이 서술하시오.\n"
        "각 항목은 최소 8문장 이상, 전체 최소 120줄 이상으로 작성하시오.\n"
        "읽는 사람이 '내 얘기다'라고 느낄 만큼 구체적으로 쓰시오.\n"
        "각 주장마다 반드시 천간·지지·십신·오행 중 하나 이상을 근거로 명시하시오.\n"
        "표면적인 설명에 그치지 말고, 그 기운이 실제 삶에서 어떤 상황과 감정으로 나타나는지 구체적인 예시를 들어 서술하시오.\n"
        "단정적이고 인상적인 문장으로 시작하여 의뢰인의 시선을 사로잡으시오.\n\n"
        + s1 + "\n\n" + s2 + "\n\n" + s3 + "\n\n" + s4 + "\n\n" + s5 + "\n\n" + s6 + closing
    )


def make_sinnyeon_prompt(man_age):
    ag = age_group(man_age)

    career_sec = ""
    if ag == 'youth':
        career_sec = "학업 및 진로운\n올해 학업·첫 취업에 유리한 흐름과 주의할 시기를 서술하시오."
    elif ag in ('prime', 'middle'):
        career_sec = "직업 및 커리어운\n올해 커리어 변화의 흐름과 이직·창업에 기운이 좋은 시기를 상·하반기로 서술하시오."
    else:
        career_sec = "활동 및 역할운\n올해 사회·가족 안에서 이 사람이 맡게 될 역할의 흐름과 무리 없이 지낼 방법을 서술하시오."

    love_sec = ""
    if ag == 'youth':
        love_sec = "인연 및 대인관계운\n올해 인연이 나타날 수 있는 시기와 대인관계의 흐름을 서술하시오."
    elif ag == 'prime':
        love_sec = "애정 및 인간관계운\n올해 인연·결혼운의 흐름과 관계 변화가 일어날 수 있는 시기를 상·하반기로 서술하시오."
    elif ag == 'middle':
        love_sec = "가족 및 인간관계운\n올해 배우자·자녀와의 관계 흐름과 주변 인간관계에서 주의할 점을 서술하시오."
    else:
        love_sec = "가족 관계운\n올해 자녀·손자·배우자와의 관계 흐름과 평안하게 지낼 방법을 서술하시오."

    health_sec = "건강운\n올해 세운의 기운이 신체 어느 부위에 영향을 주는지 분석하고 개운법을 제시하시오."

    return (
        "아래 항목을 순서대로 빠짐없이 서술하시오. 전체 최소 100줄 이상으로 작성하시오.\n"
        "각 항목마다 천간·지지·십신·오행 근거를 명시하고, 실제 삶의 상황으로 구체화하시오.\n\n"
        "2026년 총운\n"
        "丙火(병화)와 午火(오화)가 이 사주와 어떤 관계를 형성하는지,\n"
        "올해가 기회·안정·변화 중 어떤 해인지 명확히 짚어주시오.\n\n"
        "재물 및 경제운\n"
        "올해 재물 기운이 강한 시기와 지출을 단속해야 할 시기를 상·하반기 흐름으로 서술하시오.\n\n"
        + career_sec + "\n\n"
        + love_sec + "\n\n"
        + health_sec + "\n\n"
        "2026년 상·하반기 운세\n"
        "상반기와 하반기 각각의 기운과 특히 주의할 시기를 서술하시오. 특정 날짜나 월을 단정 짓지 마시오.\n\n"
        "2026년 행운 가이드\n"
        "행운의 방향·색·숫자, 반드시 해야 할 것 두 가지와 피해야 할 것 두 가지를 서술하시오.\n\n"
        "마지막은 2026년을 앞둔 이 사람에게 전하는 따뜻하고 진심 어린 한 마디로 마무리하시오."
    )


def make_love_prompt(man_age):
    ag = age_group(man_age)

    if ag == 'elder':
        return (
            "아래 항목을 순서대로 빠짐없이 서술하시오. 전체 최소 80줄 이상으로 작성하시오.\n"
            "각 항목마다 천간·지지·십신·오행 근거를 명시하고, 실제 삶의 상황으로 구체화하시오.\n\n"
            "관계운 총론\n"
            "이 사주에서 가족·주변 사람과의 인연이 형성되는 방식과 반복되는 관계 패턴을 서술하시오.\n\n"
            "배우자 및 가족 관계\n"
            "배우자성의 위치로 본 현재 부부 관계의 흐름과 조화롭게 지내는 방법을 서술하시오.\n"
            "자녀·손자와의 인연이 어떤 기운으로 흐르는지 짚어주시오.\n\n"
            "2026년 관계운\n"
            "올해 가족·주변 관계에서 특히 주의해야 할 시기와 화합하기 좋은 흐름을 상·하반기로 서술하시오.\n\n"
            "대인관계 솔루션\n"
            "갈등이 생기기 쉬운 살(煞)이나 합(合)의 작용과 관계 개선 방법을 제시하시오.\n\n"
            "마지막은 유도령이 이 사람의 인연에 대해 전하는 진심 어린 한 마디로 마무리하시오."
        )

    return (
        "아래 항목을 순서대로 빠짐없이 서술하시오. 전체 최소 90줄 이상으로 작성하시오.\n"
        "각 항목마다 천간·지지·십신·오행 근거를 명시하고, 실제 삶의 상황으로 구체화하시오.\n\n"
        "연애운 총론\n"
        "도화살(桃花殺)·홍염살·배우자성의 위치와 기운을 분석하시오.\n"
        "이 사람이 사랑에서 반복하는 패턴과 그 근거를 사주로 설명하시오.\n\n"
        "연애 스타일\n"
        "이 사람이 끌리는 상대 유형과 실제로 잘 맞는 상대의 오행·일간 차이를 설명하시오.\n"
        "연애할 때 강점과 주의해야 할 습관을 짚어주시오.\n\n"
        "결혼 및 배우자운\n"
        "배우자성의 위치로 본 인연이 나타나는 시기와 배우자의 특징을 서술하시오.\n"
        "결혼에 유리한 시기와 조심해야 할 시기를 대략적인 흐름으로 안내하시오.\n\n"
        "2026년 연애운\n"
        "올해 인연이 들어오거나 관계 변화가 일어날 수 있는 시기를 상·하반기 흐름으로 서술하시오.\n\n"
        "대인관계 솔루션\n"
        "갈등이 생기기 쉬운 살(煞)이나 합(合)의 작용과 관계 개선 방법을 제시하시오.\n\n"
        "마지막은 유도령이 이 사람의 인연에 대해 전하는 진심 어린 한 마디로 마무리하시오."
    )

# ─── 캐시 ───────────────────────────────────────────────────────────
BASE_CACHE     = {}
DETAIL_CACHE   = {}
SINNYEON_CACHE = {}
LOVE_CACHE     = {}

# ─── 라우트 ─────────────────────────────────────────────────────────
def get_cumulative_count():
    import datetime, hashlib
    base = 12000
    start = datetime.date(2026, 3, 17)
    today = datetime.date.today()
    days = max(0, (today - start).days)
    total = base
    for i in range(days):
        day = start + datetime.timedelta(days=i)
        seed = int(hashlib.md5(str(day).encode()).hexdigest(), 16)
        total += 5 + (seed % 46)
    return total

@app.route('/count')
def count():
    return jsonify({'count': get_cumulative_count()})

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/refund')
def refund():
    return render_template('refund.html')

@app.route('/loading')
def loading_page():
    return render_template('loading.html')

@app.route('/result')
def result_page():
    return render_template('result.html')

@app.route('/payment/return')
def payment_return():
    import requests as req
    from urllib.parse import quote
    imp_uid     = request.args.get('imp_uid', '')
    imp_success = request.args.get('imp_success', 'false')
    error_msg   = request.args.get('error_msg', '')
    if imp_success == 'true' and imp_uid:
        try:
            token_res = req.post('https://api.iamport.kr/users/getToken', json={
                'imp_key': os.environ.get('PORTONE_API_KEY', ''),
                'imp_secret': os.environ.get('PORTONE_API_SECRET', '')
            }, timeout=10)
            token_data = token_res.json()
            if token_data.get('code') == 0:
                access_token = token_data['response']['access_token']
                pay_res = req.get(
                    f'https://api.iamport.kr/payments/{imp_uid}',
                    headers={'Authorization': access_token}, timeout=10
                )
                p = pay_res.json().get('response') or {}
                if p.get('status') == 'paid' and p.get('amount') == 9900:
                    return redirect('/result?payment_done=1')
                return redirect('/result?payment_failed=1&error_msg=' + quote(f"상태:{p.get('status')} 금액:{p.get('amount')}"))
        except Exception:
            traceback.print_exc()
    return redirect('/result?payment_failed=1&error_msg=' + quote(error_msg or '결제 검증 실패'))

@app.route('/payment/verify', methods=['POST'])
def payment_verify():
    import requests as req
    data    = request.json
    imp_uid = data.get('imp_uid', '')
    if not imp_uid:
        return jsonify({'verified': False, 'message': '결제 정보가 없습니다'}), 400
    try:
        token_res = req.post('https://api.iamport.kr/users/getToken', json={
            'imp_key': os.environ.get('PORTONE_API_KEY', ''),
            'imp_secret': os.environ.get('PORTONE_API_SECRET', '')
        }, timeout=10)
        token_data = token_res.json()
        if token_data.get('code') != 0:
            return jsonify({'verified': False, 'message': f"포트원 인증 실패: {token_data.get('message', '')}"})

        access_token = token_data['response']['access_token']
        pay_res = req.get(
            f'https://api.iamport.kr/payments/{imp_uid}',
            headers={'Authorization': access_token}, timeout=10
        )
        p = pay_res.json().get('response') or {}
        if p.get('status') == 'paid' and p.get('amount') == 9900:
            return jsonify({'verified': True})
        return jsonify({'verified': False, 'message': f"상태: {p.get('status')}, 금액: {p.get('amount')}"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'verified': False, 'message': str(e)})

@app.route('/saju')
def saju_page():
    return render_template('saju_input.html')

@app.route('/sinnyeon')
def sinnyeon_page():
    return render_template('sinnyeon.html')

@app.route('/love')
def love_page():
    return render_template('love.html')

# ── 정통사주 맛보기 ──────────────────────────────────────────────────
@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    gender, name = data['gender'], data['name']
    birth, time  = parse_birth_params(data)
    base_key     = make_key(gender, birth, time)
    try:
        if base_key not in BASE_CACHE:
            parts = birth.split('-')
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            hour, ampm = parse_time(time)
            saju_flat, saju_str = calc_saju(year, month, day, hour, ampm)
            ilgan  = saju_flat.get('일주천간', {})
            iljiji = saju_flat.get('일주지지', {})
            man_age, korean_age = calc_age(birth)
            age_str = f" / 만 {man_age}세, 한국 나이 {korean_age}세" if man_age is not None else ""
            prompt = (
                f"{name}님 사주: {gender} / {birth}{age_str} / {saju_str}\n"
                f"일주: {ilgan.get('hanja','?')}({ilgan.get('oheng','?')}) "
                f"{iljiji.get('hanja','?')}({iljiji.get('oheng','?')})\n\n"
                f"{name}님의 사주를 바탕으로 타고난 기질과 운명의 큰 줄기, 재물·인연의 흐름을 5~6문장으로 서술하시오. "
                f"명리학 용어를 써서 구체적으로, 막연한 표현은 절대 금지하오. "
                f"특정 연도를 단정 짓지 마시오. 소항목 제목은 붙이지 마시오. 나이 언급 시 위에 제공된 만 나이를 그대로 사용하시오. 내용을 반복하지 마시오."
            )
            preview = trim_preview(call_gemini(prompt), max_sentences=6)
            BASE_CACHE[base_key] = {'saju': saju_flat, 'saju_str': saju_str, 'preview': preview}

        cached = BASE_CACHE[base_key]
        return jsonify({'saju': cached['saju'], 'preview': cached.get('preview', '')})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ── 정통사주 상세 ────────────────────────────────────────────────────
@app.route('/pay_analyze', methods=['POST'])
def pay_analyze():
    data = request.json
    gender, name = data['gender'], data['name']
    birth, time  = parse_birth_params(data)
    base_key     = make_key(gender, birth, time)
    detail_key   = make_key('detail', gender, birth, time)
    try:
        if base_key not in BASE_CACHE:
            parts = birth.split('-')
            yr, mo, dy = int(parts[0]), int(parts[1]), int(parts[2])
            hour, ampm = parse_time(time)
            sf, ss = calc_saju(yr, mo, dy, hour, ampm)
            BASE_CACHE[base_key] = {'saju': sf, 'saju_str': ss, 'preview': ''}
        saju_str = BASE_CACHE[base_key]['saju_str']
        if detail_key not in DETAIL_CACHE:
            man_age, korean_age = calc_age(birth)
            age_str = f" / 만 {man_age}세, 한국 나이 {korean_age}세" if man_age is not None else ""
            prompt = (
                DETAIL_BASE
                + f"{name}님 정보: {name} / {gender} / {birth}{age_str} / {time}\n"
                + f"사주팔자: {saju_str}\n\n"
                + make_full_prompt(man_age)
            )
            DETAIL_CACHE[detail_key] = attach_nim(call_gemini(prompt, temperature=0.5), [name])
        return jsonify({'detail': DETAIL_CACHE[detail_key]})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ── 신년운세 맛보기 ──────────────────────────────────────────────────
@app.route('/sinnyeon_preview', methods=['POST'])
def sinnyeon_preview():
    try:
        data = request.json
        gender, name = data.get('gender',''), data.get('name','')
        birth, time  = parse_birth_params(data)
        base_key     = make_key(gender, birth, time)
        parts = birth.split('-')
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        hour, ampm = parse_time(time)
        saju_flat, saju_str = calc_saju(year, month, day, hour, ampm)
        if base_key not in BASE_CACHE:
            BASE_CACHE[base_key] = {'saju': saju_flat, 'saju_str': saju_str, 'preview': ''}
        ilgan = saju_flat.get('일주천간', {})
        man_age, korean_age = calc_age(birth)
        age_str = f" / 만 {man_age}세, 한국 나이 {korean_age}세" if man_age is not None else ""
        prompt = (
            f"{name}님 사주: {gender} / {birth}{age_str} / {saju_str}\n"
            f"일간: {ilgan.get('hanja','?')}({ilgan.get('oheng','?')})\n\n"
            f"{name}님의 2026년 병오년 신년운세 핵심을 딱 2~3문장으로만 서술하시오. "
            f"병오년의 기운이 이 사주에 어떻게 작용하는지 명리학 용어로 구체적으로 쓰시오."
        )
        preview = trim_preview(call_gemini(prompt))
        return jsonify({'saju': saju_flat, 'preview': preview})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ── 신년운세 상세 ────────────────────────────────────────────────────
@app.route('/sinnyeon_detail', methods=['POST'])
def sinnyeon_detail():
    data = request.json
    gender, name = data['gender'], data['name']
    birth, time  = parse_birth_params(data)
    skey         = make_key('sinnyeon', gender, birth, time)
    base_key     = make_key(gender, birth, time)
    try:
        if base_key not in BASE_CACHE:
            parts = birth.split('-')
            yr, mo, dy = int(parts[0]), int(parts[1]), int(parts[2])
            hour, ampm = parse_time(time)
            sf, ss = calc_saju(yr, mo, dy, hour, ampm)
            BASE_CACHE[base_key] = {'saju': sf, 'saju_str': ss, 'preview': ''}
        saju_str = BASE_CACHE[base_key]['saju_str']
        if skey not in SINNYEON_CACHE:
            man_age, korean_age = calc_age(birth)
            age_str = f" / 만 {man_age}세, 한국 나이 {korean_age}세" if man_age is not None else ""
            prompt = (
                DETAIL_BASE
                + f"{name}님 정보: {name} / {gender} / {birth}{age_str} / {time}\n"
                + f"사주팔자: {saju_str}\n\n"
                + make_sinnyeon_prompt(man_age)
            )
            SINNYEON_CACHE[skey] = attach_nim(call_gemini(prompt, temperature=0.5), [name])
        return jsonify({'detail': SINNYEON_CACHE[skey]})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ── 연애운세 맛보기 ──────────────────────────────────────────────────
@app.route('/love_preview', methods=['POST'])
def love_preview():
    try:
        data = request.json
        gender, name  = data.get('gender',''), data.get('name','')
        love_status   = data.get('love_status', '')
        love_question = data.get('love_question', '')
        birth, time   = parse_birth_params(data)
        parts = birth.split('-')
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        hour, ampm = parse_time(time)
        saju_flat, saju_str = calc_saju(year, month, day, hour, ampm)
        ilgan = saju_flat.get('일주천간', {})
        man_age, korean_age = calc_age(birth)
        age_str = f" / 만 {man_age}세, 한국 나이 {korean_age}세" if man_age is not None else ""
        prompt = (
            f"{name}님 사주: {gender} / {birth}{age_str} / {saju_str}\n"
            f"일간: {ilgan.get('hanja','?')}({ilgan.get('oheng','?')})\n"
            f"현재 연애 상태: {love_status}\n"
            f"가장 궁금한 것: {love_question}\n\n"
            f"{name}님의 연애운 핵심을 딱 2~3문장으로만 서술하시오. "
            f"도화살과 배우자성의 기운을 명리학 용어로 구체적으로 쓰시오."
        )
        preview = trim_preview(call_gemini(prompt))
        return jsonify({'saju': saju_flat, 'preview': preview})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ── 연애운세 상세 ────────────────────────────────────────────────────
@app.route('/love_detail', methods=['POST'])
def love_detail():
    data = request.json
    gender, name  = data['gender'], data['name']
    love_status   = data.get('love_status', '')
    love_question = data.get('love_question', '')
    birth, time   = parse_birth_params(data)
    lkey          = make_key('love', gender, birth, time, love_status, love_question)
    base_key      = make_key(gender, birth, time)
    try:
        if base_key not in BASE_CACHE:
            parts = birth.split('-')
            yr, mo, dy = int(parts[0]), int(parts[1]), int(parts[2])
            hour, ampm = parse_time(time)
            sf, ss = calc_saju(yr, mo, dy, hour, ampm)
            BASE_CACHE[base_key] = {'saju': sf, 'saju_str': ss, 'preview': ''}
        saju_str = BASE_CACHE[base_key]['saju_str']
        if lkey not in LOVE_CACHE:
            man_age, korean_age = calc_age(birth)
            age_str = f" / 만 {man_age}세, 한국 나이 {korean_age}세" if man_age is not None else ""
            prompt = (
                DETAIL_BASE
                + f"{name}님 정보: {name} / {gender} / {birth}{age_str} / {time}\n"
                + f"사주팔자: {saju_str}\n"
                + f"현재 연애 상태: {love_status}\n"
                + f"가장 궁금한 것: {love_question}\n\n"
                + make_love_prompt(man_age)
            )
            LOVE_CACHE[lkey] = attach_nim(call_gemini(prompt, temperature=0.5), [name])
        return jsonify({'detail': LOVE_CACHE[lkey]})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ── 캐시 초기화 ──────────────────────────────────────────────────────
@app.route('/clear_cache', methods=['POST'])
def clear_cache():
    BASE_CACHE.clear(); DETAIL_CACHE.clear()
    SINNYEON_CACHE.clear(); LOVE_CACHE.clear()
    return jsonify({"ok": True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG','false').lower()=='true')
