import os, re, hashlib, traceback
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types
from flask import Flask, render_template, request, jsonify
from saju_logic import calc_saju, lunar_to_solar

app = Flask(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

SYSTEM_MSG = (
    "당신은 수십 년 경력의 명리학자 유도령이오. "
    "위엄 있는 도사님 말투(~하오, ~이니라, ~할 것이오)를 한결같이 쓰시오. "
    "인공지능, 데이터, AI 같은 단어는 절대 금지하오. "
    "이모지나 특수기호는 쓰지 마시오. "
    "의뢰인을 부를 때는 반드시 이름 뒤에 님을 붙이시오. "
    "반드시 한국어로만 작성하시오. 영어 단어, 영문 약어, 로마자 표기는 일절 사용하지 마시오."
)

def call_gemini(prompt, temperature=0.6):
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_MSG,
            temperature=temperature,
        )
    )
    return response.text

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
    "이모지, 별표(**), 밑줄(__), 특수기호 일절 사용하지 마시오.\n"
    "인공지능, 데이터, AI, 알고리즘 같은 단어는 절대 쓰지 마시오.\n"
    "한자를 쓸 때는 반드시 괄호 안에 한글 독음을 병기하시오.\n"
    "항목 구분이 필요하면 빈 줄로만 구분하고 제목 앞에 어떤 기호도 붙이지 마시오.\n"
    "반드시 한국어로만 작성하시오. 영어 단어, 영문 약어, 로마자 표기는 일절 사용하지 마시오.\n\n"
)

# ─── 프롬프트 ────────────────────────────────────────────────────────

FULL_ANALYSIS_PROMPT = """
아래 6개 카테고리를 순서대로 빠짐없이 서술하시오.
각 항목은 최소 5문장 이상, 전체 최소 80줄 이상으로 작성하시오.
읽는 사람이 "내 얘기다"라고 느낄 만큼 구체적으로 쓰시오.

1. 선천적 기질 및 성향

나의 핵심 오행: 일간을 중심으로 이 사람이 타고난 본연의 기질과 성질을 서술하시오.
심리 분석: 십신(十神)을 통한 성격 장단점과 무의식적으로 반복하는 행동 패턴을 짚어주시오.
사회적 페르소나: 타인에게 보여지는 겉모습과 실제 내면의 차이를 사주 근거와 함께 설명하시오.

2. 재물 및 경제운

재물 그릇의 크기: 정재(正財)와 편재(偏財)의 배치로 본 타고난 자산 규모와 돈을 모으는 방식을 서술하시오.
투자 성향: 공격적 투자와 안정적 저축 중 이 사주에 맞는 방식과 그 이유를 설명하시오.
재테크 시점: 재물이 들어오기 좋은 시기와 지출을 단속해야 하는 시기를 연도별·월별로 구체적으로 안내하시오.

3. 직업 및 커리어

천직과 직업군: 관성(官星)과 식상(食傷)의 배치로 본 유리한 산업군과 직업 유형을 추천하시오.
직장 내 처세: 상사·동료와의 관계 패턴 및 승진운의 흐름을 서술하시오.
이직 및 창업 타이밍: 변화를 주기에 가장 기운이 좋은 시기와 피해야 할 시기를 명확히 짚어주시오.

4. 애정 및 인간관계

연애 스타일: 이 사람이 끌리는 상대 유형과 실제로 잘 맞는 상대의 차이를 사주로 설명하시오.
결혼 및 배우자운: 인연이 나타나는 시기와 배우자의 오행·일간 특징을 서술하시오.
대인관계 솔루션: 관계에서 갈등이 생기기 쉬운 살(煞)이나 합(合)의 작용과 개선 방법을 제시하시오.

5. 건강 및 라이프스타일

취약한 신체 부위: 오행의 과다·결핍에 따라 주의해야 할 신체 부위와 질환을 설명하시오.
맞춤형 개운법: 부족한 기운을 채워주는 행운의 색상·숫자·방향·음식을 구체적으로 안내하시오.
멘탈 관리: 스트레스에 취약한 시기와 마음을 다스리는 방법을 서술하시오.

6. 주기별 상세 운세

대운 분석: 현재 대운(大運)의 흐름 속에서 이 사람이 인생의 어느 단계에 있는지 설명하시오.
2026년 월별 운세: 병오년(丙午年) 1월부터 12월까지 각 달의 기운을 최소 두 문장씩 서술하시오.
인생의 골든타임: 중요한 결정을 내리기에 가장 길한 시기를 구체적으로 짚어주시오.

마지막은 유도령이 이 사람의 삶 전체를 꿰뚫어 본 뒤 전하는 진심 어린 한 마디로 마무리하시오.
"""

SINNYEON_PROMPT = """
아래 항목을 순서대로 빠짐없이 서술하시오. 전체 최소 70줄 이상으로 작성하시오.

2026년 총운
丙火(병화)와 午火(오화)가 이 사주에 어떤 관계를 형성하는지,
올해가 기회·안정·변화 중 어떤 해인지 명확히 짚어주시오.

재물 및 경제운
올해 재물이 강하게 들어오는 달과 지출을 단속해야 하는 달을 구체적으로 서술하시오.
투자·저축 중 올해 이 사주에 유리한 방향을 설명하시오.

직업 및 커리어운
올해 커리어 변화 시기, 이직·창업에 유리한 달과 피해야 할 시기를 서술하시오.

애정 및 인간관계운
올해 인연이 들어오는 시기를 월 단위로 구체적으로 짚어주시오.
현재 연애 중이라면 관계의 흐름과 결혼운을 함께 서술하시오.

건강운
올해 세운의 기운이 신체 어느 부위에 영향을 주는지 분석하고 개운법을 제시하시오.

월별 운세 — 1월부터 12월까지
각 달의 기운을 최소 두 문장 이상으로 구체적으로 서술하시오.

2026년 행운 가이드
행운의 방향·색·숫자, 반드시 해야 할 것 두 가지와 피해야 할 것 두 가지를 서술하시오.

마지막은 2026년을 앞둔 이 사람에게 전하는 따뜻하고 진심 어린 한 마디로 마무리하시오.
"""

LOVE_PROMPT = """
아래 항목을 순서대로 빠짐없이 서술하시오. 전체 최소 60줄 이상으로 작성하시오.

연애운 총론
도화살(桃花殺)·홍염살·배우자성의 위치와 기운을 분석하시오.
이 사람이 사랑에서 반복하는 패턴과 그 근거를 사주로 설명하시오.

연애 스타일
이 사람이 끌리는 상대 유형과 실제로 잘 맞는 상대의 오행·일간 차이를 설명하시오.
연애할 때 강점과 주의해야 할 습관을 짚어주시오.

결혼 및 배우자운
배우자성의 위치로 본 인연이 나타나는 시기와 배우자의 특징을 서술하시오.
결혼에 유리한 시기와 조심해야 할 시기를 연도별로 안내하시오.

2026년 연애운
올해 인연이 들어오거나 관계 변화가 일어날 시기를 월 단위로 서술하시오.
이별·재회·고백의 적합 시기를 사주 근거와 함께 설명하시오.

대인관계 솔루션
갈등이 생기기 쉬운 살(煞)이나 합(合)의 작용과 관계 개선 방법을 제시하시오.

마지막은 유도령이 이 사람의 인연에 대해 전하는 진심 어린 한 마디로 마무리하시오.
"""

# ─── 캐시 ───────────────────────────────────────────────────────────
BASE_CACHE     = {}
DETAIL_CACHE   = {}
SINNYEON_CACHE = {}
LOVE_CACHE     = {}

# ─── 라우트 ─────────────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/loading')
def loading_page():
    return render_template('loading.html')

@app.route('/result')
def result_page():
    return render_template('result.html')

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
            prompt = (
                f"{name}님 사주: {gender} / {birth} / {saju_str}\n"
                f"일주: {ilgan.get('hanja','?')}({ilgan.get('oheng','?')}) "
                f"{iljiji.get('hanja','?')}({iljiji.get('oheng','?')})\n\n"
                f"{name}님의 사주를 바탕으로 타고난 기질과 올해 운세의 핵심을 딱 2~3문장으로만 서술하시오. "
                f"명리학 용어를 써서 구체적으로, 막연한 표현은 절대 금지하오."
            )
            preview = trim_preview(call_gemini(prompt))
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
            prompt = (
                DETAIL_BASE
                + f"{name}님 정보: {name} / {gender} / {birth} / {time}\n"
                + f"사주팔자: {saju_str}\n\n"
                + FULL_ANALYSIS_PROMPT
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
        prompt = (
            f"{name}님 사주: {gender} / {birth} / {saju_str}\n"
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
            prompt = (
                DETAIL_BASE
                + f"{name}님 정보: {name} / {gender} / {birth} / {time}\n"
                + f"사주팔자: {saju_str}\n\n"
                + SINNYEON_PROMPT
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
        prompt = (
            f"{name}님 사주: {gender} / {birth} / {saju_str}\n"
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
            prompt = (
                DETAIL_BASE
                + f"{name}님 정보: {name} / {gender} / {birth} / {time}\n"
                + f"사주팔자: {saju_str}\n"
                + f"현재 연애 상태: {love_status}\n"
                + f"가장 궁금한 것: {love_question}\n\n"
                + LOVE_PROMPT
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
    app.run(host='0.0.0.0', port=port, debug=False)
