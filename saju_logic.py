def analyze_saju(name, birth, time_known):
    print(f"\n[시스템] {name}님의 데이터를 분석 중입니다...")
    
    # 시간 모름 처리 로직
    if not time_known:
        time_status = "시간 미상 (삼주 분석 적용)"
    else:
        time_status = "시간 포함 (사주 분석 적용)"
        
    print(f"[알림] 분석 모드: {time_status}")
    
    # 수익화 분기점 시뮬레이션
    summary = f"{name}님은 타고난 재복이 있으나, 인내심이 필요한 사주입니다."
    premium_content = "상세 분석: 올해 하반기에 문서운이 들어와 부동산 계약에 유리합니다."
    
    return summary, premium_content

# --- 실제 실행 영역 ---
user_name = input("이름: ")
user_birth = input("생년월일(8자리): ")
is_time_known = input("태어난 시간을 아시나요? (y/n): ").lower() == 'y'

free_res, pay_res = analyze_saju(user_name, user_birth, is_time_known)

print(f"\n[무료 요약]: {free_res}")
print("-" * 30)
confirm = input("3,900원을 결제하고 상세 내용을 보시겠습니까? (y/n): ")

if confirm.lower() == 'y':
    print(f"\n[유료 상세]: {pay_res}")
else:
    print("\n결제가 완료되지 않았습니다.")