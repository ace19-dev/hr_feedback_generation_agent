"""
generate_mock_data.py - 테스트용 목(Mock) 데이터 일괄 생성 스크립트

실행: python generate_mock_data.py
출력: data/mock/ 하위에 6개의 JSON 파일 생성

포함된 엣지 케이스:
  1. E003 박지훈 - 1on1 이력이 Q1만 존재 (누락 분기 처리 테스트)
  2. E002 이수진 - S등급인데 피드백 코멘트가 부정적 (grade vs comment 불일치 테스트)
  3. E005 정우성 - 피드백 초안에 타 팀원(박지훈) 업무가 혼재될 수 있는 시나리오
"""

import sys
import json
import os
from pathlib import Path

# Windows 콘솔에서 한글이 깨지지 않도록 UTF-8로 강제 설정합니다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# config에서 경로 가져오기 (디렉터리 자동 생성 포함)
from config import MOCK_DATA_DIR

# ─────────────────────────────────────────────
# 1. 직원 기본정보 (employees.json)
# ─────────────────────────────────────────────
employees = [
    {
        "emp_id": "E001",
        "name": "김민준",
        "role": "Senior Engineer",
        "level": "G4",           # 직급 (G1=인턴, G5=팀장)
        "team": "AI개발팀",
        "department": "기술본부",
        "is_manager": False,
        "manager_id": "E006",
        "join_date": "2020-03-02",
        "email": "minjun.kim@company.com",
        "specialty": "ML 모델 최적화, MLOps 파이프라인"
    },
    {
        "emp_id": "E002",
        "name": "이수진",
        "role": "Engineer",
        "level": "G3",
        "team": "AI개발팀",
        "department": "기술본부",
        "is_manager": False,
        "manager_id": "E006",
        "join_date": "2021-07-01",
        "email": "sujin.lee@company.com",
        "specialty": "데이터 파이프라인, 백엔드 API"
    },
    {
        # 엣지케이스 - Q1 1on1만 존재
        "emp_id": "E003",
        "name": "박지훈",
        "role": "Junior Engineer",
        "level": "G2",
        "team": "AI개발팀",
        "department": "기술본부",
        "is_manager": False,
        "manager_id": "E006",
        "join_date": "2023-01-02",
        "email": "jihun.park@company.com",
        "specialty": "프론트엔드, 유닛 테스트"
    },
    {
        "emp_id": "E004",
        "name": "최하은",
        "role": "Engineer",
        "level": "G3",
        "team": "AI개발팀",
        "department": "기술본부",
        "is_manager": False,
        "manager_id": "E006",
        "join_date": "2022-04-04",
        "email": "haeun.choi@company.com",
        "specialty": "시스템 모니터링, SRE"
    },
    {
        # 엣지케이스 - 타 팀원 업무가 혼재될 수 있는 시나리오
        "emp_id": "E005",
        "name": "정우성",
        "role": "Senior Engineer",
        "level": "G4",
        "team": "AI개발팀",
        "department": "기술본부",
        "is_manager": False,
        "manager_id": "E006",
        "join_date": "2019-08-05",
        "email": "woosung.jung@company.com",
        "specialty": "시스템 아키텍처, 성능 튜닝"
    },
    {
        "emp_id": "E006",
        "name": "한지영",
        "role": "Team Lead",
        "level": "G5",
        "team": "AI개발팀",
        "department": "기술본부",
        "is_manager": True,
        "manager_id": None,    # 팀장은 상위자 없음
        "join_date": "2018-02-01",
        "email": "jiyoung.han@company.com",
        "specialty": "팀 관리, 기술 전략, AI 서비스 기획"
    }
]

# ─────────────────────────────────────────────
# 2. KPI 및 연간 업무계획 (kpi_plans.json)
# ─────────────────────────────────────────────
kpi_plans = [
    # E001 김민준 - 목표 달성률 높음, B+ 예상
    {
        "emp_id": "E001",
        "year": 2025,
        "kpi_items": [
            {
                "kpi_id": "K001-1",
                "category": "업적",
                "title": "추천 모델 정확도 향상",
                "target": "NDCG@10 기준 0.72 이상 달성",
                "target_value": 0.72,
                "achievement_value": 0.748,   # 초과 달성
                "achievement_rate": 103.9,
                "weight": 35
            },
            {
                "kpi_id": "K001-2",
                "category": "업적",
                "title": "API 레이턴시 개선",
                "target": "P95 레이턴시 200ms 이하 달성",
                "target_value": 200,
                "achievement_value": 178,
                "achievement_rate": 111.0,
                "weight": 25
            },
            {
                "kpi_id": "K001-3",
                "category": "역량",
                "title": "코드 리뷰 기여",
                "target": "주당 평균 5건 이상 리뷰",
                "target_value": 5,
                "achievement_value": 4.8,    # 미달
                "achievement_rate": 96.0,
                "weight": 20
            },
            {
                "kpi_id": "K001-4",
                "category": "역량",
                "title": "주니어 멘토링",
                "target": "신규 입사자 2명 이상 멘토링",
                "target_value": 2,
                "achievement_value": 2,
                "achievement_rate": 100.0,
                "weight": 20
            }
        ]
    },
    # E002 이수진 - 엣지케이스: S등급이지만 면담 코멘트는 부정적
    {
        "emp_id": "E002",
        "year": 2025,
        "kpi_items": [
            {
                "kpi_id": "K002-1",
                "category": "업적",
                "title": "실시간 데이터 파이프라인 구축",
                "target": "일 처리량 1M 이벤트 이상, 지연 5초 이내",
                "target_value": 1000000,
                "achievement_value": 1500000,  # 큰 폭 초과 달성
                "achievement_rate": 150.0,
                "weight": 40
            },
            {
                "kpi_id": "K002-2",
                "category": "업적",
                "title": "테스트 커버리지 향상",
                "target": "팀 평균 커버리지 80% 이상",
                "target_value": 80,
                "achievement_value": 87,
                "achievement_rate": 108.8,
                "weight": 30
            },
            {
                "kpi_id": "K002-3",
                "category": "역량",
                "title": "기술 문서 작성",
                "target": "주요 컴포넌트 5개 이상 문서화",
                "target_value": 5,
                "achievement_value": 5,
                "achievement_rate": 100.0,
                "weight": 30
            }
        ]
    },
    # E003 박지훈 - 엣지케이스: Q1만 1on1 기록
    {
        "emp_id": "E003",
        "year": 2025,
        "kpi_items": [
            {
                "kpi_id": "K003-1",
                "category": "업적",
                "title": "신규 기능 개발",
                "target": "할당된 스프린트 기능 90% 이상 완료",
                "target_value": 90,
                "achievement_value": 85,
                "achievement_rate": 94.4,
                "weight": 50
            },
            {
                "kpi_id": "K003-2",
                "category": "역량",
                "title": "버그 수정 처리율",
                "target": "배정 버그 100% 기한 내 처리",
                "target_value": 100,
                "achievement_value": 90,
                "achievement_rate": 90.0,
                "weight": 30
            },
            {
                "kpi_id": "K003-3",
                "category": "역량",
                "title": "기술 학습",
                "target": "사내 기술 교육 3회 이상 수료",
                "target_value": 3,
                "achievement_value": 2,   # 미달
                "achievement_rate": 66.7,
                "weight": 20
            }
        ]
    },
    # E004 최하은 - 보통 성과
    {
        "emp_id": "E004",
        "year": 2025,
        "kpi_items": [
            {
                "kpi_id": "K004-1",
                "category": "업적",
                "title": "서비스 가용성 향상",
                "target": "월간 가용성 99.9% 이상 유지",
                "target_value": 99.9,
                "achievement_value": 99.95,
                "achievement_rate": 100.1,
                "weight": 40
            },
            {
                "kpi_id": "K004-2",
                "category": "업적",
                "title": "모니터링 대시보드 구축",
                "target": "Grafana 대시보드 핵심 지표 10개 이상 시각화",
                "target_value": 10,
                "achievement_value": 12,
                "achievement_rate": 120.0,
                "weight": 35
            },
            {
                "kpi_id": "K004-3",
                "category": "역량",
                "title": "인시던트 대응",
                "target": "P1 인시던트 MTTR 30분 이내",
                "target_value": 30,
                "achievement_value": 35,
                "achievement_rate": 85.7,
                "weight": 25
            }
        ]
    },
    # E005 정우성 - 높은 성과, A 예상
    {
        "emp_id": "E005",
        "year": 2025,
        "kpi_items": [
            {
                "kpi_id": "K005-1",
                "category": "업적",
                "title": "마이크로서비스 아키텍처 전환",
                "target": "핵심 서비스 3개 이상 MSA 전환 완료",
                "target_value": 3,
                "achievement_value": 4,
                "achievement_rate": 133.3,
                "weight": 45
            },
            {
                "kpi_id": "K005-2",
                "category": "업적",
                "title": "DB 쿼리 성능 최적화",
                "target": "슬로우 쿼리 80% 이상 개선",
                "target_value": 80,
                "achievement_value": 92,
                "achievement_rate": 115.0,
                "weight": 30
            },
            {
                "kpi_id": "K005-3",
                "category": "역량",
                "title": "아키텍처 리뷰 주도",
                "target": "분기별 아키텍처 리뷰 세션 진행",
                "target_value": 4,
                "achievement_value": 4,
                "achievement_rate": 100.0,
                "weight": 25
            }
        ]
    }
]

# ─────────────────────────────────────────────
# 3. 분기별 1on1 면담 이력 (1on1_records.json)
# ─────────────────────────────────────────────
one_on_one_records = [
    # E001 김민준 - Q1~Q4 모두 정상
    {"emp_id": "E001", "year": 2025, "quarter": "Q1", "date": "2025-03-20",
     "manager_id": "E006",
     "agenda": ["Q1 KPI 점검", "모델 정확도 개선 계획", "팀 내 역할 논의"],
     "discussion": "추천 모델 실험 4가지 시도 중 2가지 성공. NDCG 0.71 달성. API 레이턴시는 아직 목표 미달(230ms). 멘토링 관련 박지훈 온보딩 진행 중.",
     "action_items": ["4월까지 피처 엔지니어링 추가 실험", "레이턴시 병목 구간 프로파일링"],
     "manager_feedback": "Q1 성과 긍정적. 모델 실험에서 좋은 결과. 레이턴시 개선에 더 집중 필요."},

    {"emp_id": "E001", "year": 2025, "quarter": "Q2", "date": "2025-06-18",
     "manager_id": "E006",
     "agenda": ["Q2 중간 점검", "API 성능 개선 현황", "하반기 목표 조정"],
     "discussion": "API 레이턴시 198ms 달성, 목표 거의 달성. 모델 NDCG 0.735로 상승. 코드 리뷰 주당 4.5건으로 목표 대비 소폭 미달. 박지훈 멘토링 좋은 평가.",
     "action_items": ["레이턴시 최적화 마무리", "코드 리뷰 참여도 높이기"],
     "manager_feedback": "전반적으로 순조로운 진행. 코드 리뷰 참여를 조금 더 늘려주면 좋겠음."},

    {"emp_id": "E001", "year": 2025, "quarter": "Q3", "date": "2025-09-17",
     "manager_id": "E006",
     "agenda": ["Q3 성과 리뷰", "연말 목표 달성 예측", "성장 방향 논의"],
     "discussion": "모델 NDCG 0.748 달성(목표 초과). API 레이턴시 178ms. 코드 리뷰 주당 4.8건. 하반기 아키텍처 개선 프로젝트 참여 희망.",
     "action_items": ["Q4 모델 A/B 테스트 기획", "아키텍처 리뷰 세션 참여"],
     "manager_feedback": "핵심 KPI 모두 목표 달성 또는 초과. 연말 B+ 등급 예상."},

    {"emp_id": "E001", "year": 2025, "quarter": "Q4", "date": "2025-12-10",
     "manager_id": "E006",
     "agenda": ["연간 성과 최종 점검", "내년 목표 설정 사전 논의"],
     "discussion": "연간 KPI 모두 목표 달성. 특히 추천 모델 정확도와 API 성능에서 탁월한 성과. 멘토링 역할도 잘 수행. 코드 리뷰만 미세하게 미달.",
     "action_items": ["내년 시니어 역할 확대 논의", "기술 블로그 작성 고려"],
     "manager_feedback": "연간 전체적으로 훌륭한 성과. B+ 확정적."},

    # E002 이수진 - 엣지케이스: 성과는 탁월(S등급)이나 1on1 내용은 부정적 표현 많음
    {"emp_id": "E002", "year": 2025, "quarter": "Q1", "date": "2025-03-14",
     "manager_id": "E006",
     "agenda": ["파이프라인 구축 계획", "팀 협업 이슈"],
     "discussion": "파이프라인 구축 시작했으나 팀원과 방향성 충돌. 커뮤니케이션 방식에 대해 팀장과 논의. 기술적 역량은 탁월하지만 협업 시 독단적 결정으로 마찰 발생.",
     "action_items": ["주요 기술 결정 전 팀 공유", "데일리 스탠드업 적극 참여"],
     "manager_feedback": "기술 실력은 뛰어나지만 팀 내 협업 방식 개선 필요."},

    {"emp_id": "E002", "year": 2025, "quarter": "Q2", "date": "2025-06-12",
     "manager_id": "E006",
     "agenda": ["파이프라인 진행 현황", "협업 개선 여부"],
     "discussion": "파이프라인 성과 매우 우수(1.5M 이벤트/일 처리). 그러나 Q1에 지적한 협업 이슈 반복. 다른 팀원의 PR에 비판적 코멘트 많음. 코드 리뷰 방식 개선 요청.",
     "action_items": ["리뷰 코멘트 톤 개선", "긍정적 피드백 비율 높이기"],
     "manager_feedback": "성과는 탁월하지만 팀 분위기에 부정적 영향. 소프트 스킬 개선 요청."},

    {"emp_id": "E002", "year": 2025, "quarter": "Q3", "date": "2025-09-10",
     "manager_id": "E006",
     "agenda": ["테스트 커버리지 현황", "리더십 역량 개발"],
     "discussion": "테스트 커버리지 87% 달성(목표 초과). 하지만 Q2 이후로도 팀 분위기 문제 지속. 협업 이슈는 나아지지 않고 있음. 기술적 성과와 팀워크 간의 gap이 뚜렷함.",
     "action_items": ["협업 역량 개발 교육 참여 권고", "팀원과 1:1 소통 늘리기"],
     "manager_feedback": "KPI 성과는 S등급 수준이지만 팀워크 부분은 지속적으로 개선 필요."},

    {"emp_id": "E002", "year": 2025, "quarter": "Q4", "date": "2025-12-08",
     "manager_id": "E006",
     "agenda": ["연간 성과 리뷰", "내년 역할 논의"],
     "discussion": "기술적 성과는 팀 최고 수준. 파이프라인 구축, 테스트 커버리지 모두 탁월. 다만 협업/소통 이슈로 인해 팀 전체 생산성에 영향. 내년에는 리더십 스킬 개발 집중 권고.",
     "action_items": ["리더십 코칭 프로그램 등록"],
     "manager_feedback": "성과는 S등급이나 팀워크 측면에서 개선 없으면 장기적 성장 제약 우려."},

    # E003 박지훈 - 엣지케이스: Q1만 존재 (Q2~Q4 기록 없음)
    {"emp_id": "E003", "year": 2025, "quarter": "Q1", "date": "2025-03-28",
     "manager_id": "E006",
     "agenda": ["온보딩 완료 점검", "Q1 목표 설정", "기술 스택 적응"],
     "discussion": "입사 2년차, 팀 문화 잘 적응 중. 할당된 스프린트 기능 개발 중 버그 수정에 시간 많이 소요. 프론트엔드 작업 속도 향상 중. 사내 기술 교육 2개 수료 완료.",
     "action_items": ["단위 테스트 작성 습관화", "시니어 김민준에게 코드 리뷰 요청"],
     "manager_feedback": "초반 온보딩 잘 마무리. 속도보다 품질에 집중하는 방향으로 진행."},
    # Q2, Q3, Q4 기록 없음 (엣지케이스 - 기록 없음으로 처리)

    # E004 최하은 - Q1~Q4 모두
    {"emp_id": "E004", "year": 2025, "quarter": "Q1", "date": "2025-03-21",
     "manager_id": "E006",
     "agenda": ["모니터링 시스템 계획", "온콜 로테이션 논의"],
     "discussion": "모니터링 대시보드 기획 중. 가용성 99.9% 목표는 안정적으로 관리 중. 인시던트 대응 시 초기 진단에 시간 소요. 학습 의지 강함.",
     "action_items": ["Grafana 대시보드 초안 작성", "인시던트 런북 문서화"],
     "manager_feedback": "안정적인 업무 처리. 인시던트 대응 속도 개선이 핵심 과제."},

    {"emp_id": "E004", "year": 2025, "quarter": "Q2", "date": "2025-06-19",
     "manager_id": "E006",
     "agenda": ["대시보드 구축 현황", "인시던트 MTTR 개선"],
     "discussion": "Grafana 대시보드 8개 지표 시각화 완료. 가용성 목표 달성 중. MTTR 35분으로 목표(30분) 미달. 두 번의 P1 인시던트에서 초기 진단 개선 필요.",
     "action_items": ["인시던트 드릴 참여", "알림 임계값 조정"],
     "manager_feedback": "대시보드 구축 잘 진행 중. MTTR 개선에 집중 필요."},

    {"emp_id": "E004", "year": 2025, "quarter": "Q3", "date": "2025-09-23",
     "manager_id": "E006",
     "agenda": ["Q3 성과 점검", "MTTR 개선 현황"],
     "discussion": "Grafana 대시보드 12개 지표 완성(목표 초과). 가용성 99.95%. MTTR은 여전히 35분 수준으로 개선 미흡. 프로세스 개선보다 도구 숙련도 문제로 파악.",
     "action_items": ["관찰 도구 추가 학습", "온콜 핸드북 업데이트"],
     "manager_feedback": "대시보드는 훌륭하게 완성. MTTR만 개선되면 B+ 가능."},

    {"emp_id": "E004", "year": 2025, "quarter": "Q4", "date": "2025-12-05",
     "manager_id": "E006",
     "agenda": ["연간 성과 리뷰", "내년 SRE 역할 강화"],
     "discussion": "모니터링 시스템 구축은 팀에 큰 기여. 가용성 목표 달성. MTTR은 끝까지 개선 미흡. 전반적으로 안정적이고 신뢰할 수 있는 역할 수행.",
     "action_items": ["내년 카오스 엔지니어링 학습"],
     "manager_feedback": "B 등급 예상. 꾸준하고 신뢰할 수 있는 기여."},

    # E005 정우성 - Q1~Q4 모두, 높은 성과
    {"emp_id": "E005", "year": 2025, "quarter": "Q1", "date": "2025-03-17",
     "manager_id": "E006",
     "agenda": ["MSA 전환 계획", "DB 성능 이슈"],
     "discussion": "마이크로서비스 전환 로드맵 작성 완료. 첫 번째 서비스(인증 서비스) 전환 착수. DB 슬로우 쿼리 분석 시작. 아키텍처 리뷰 세션 Q1 진행 완료.",
     "action_items": ["인증 서비스 MSA 전환 Q2 완료", "슬로우 쿼리 TOP 10 개선"],
     "manager_feedback": "아키텍처 전환 계획 탄탄함. 속도감 있게 진행 중."},

    {"emp_id": "E005", "year": 2025, "quarter": "Q2", "date": "2025-06-16",
     "manager_id": "E006",
     "agenda": ["MSA 전환 현황", "DB 최적화 결과"],
     "discussion": "인증/결제 서비스 2개 MSA 전환 완료. DB 슬로우 쿼리 60% 개선. 아키텍처 리뷰 Q2 진행. 팀 전체가 아키텍처 방향에 공감대 형성됨.",
     "action_items": ["Q3에 추천/알림 서비스 전환", "DB 인덱스 추가 최적화"],
     "manager_feedback": "기대 이상의 속도와 품질. A 등급 유력."},

    {"emp_id": "E005", "year": 2025, "quarter": "Q3", "date": "2025-09-15",
     "manager_id": "E006",
     "agenda": ["MSA 전환 마무리", "성능 최적화 결과"],
     "discussion": "4개 서비스 MSA 전환 완료(목표 초과). DB 슬로우 쿼리 92% 개선. 아키텍처 리뷰 세션 팀원들 만족도 높음. 전체 시스템 안정성도 함께 향상됨.",
     "action_items": ["MSA 운영 런북 작성", "Q4 아키텍처 리뷰에서 연간 성과 공유"],
     "manager_feedback": "연간 최고 수준의 기여. A 등급 확정."},

    {"emp_id": "E005", "year": 2025, "quarter": "Q4", "date": "2025-12-11",
     "manager_id": "E006",
     "agenda": ["연간 성과 리뷰", "내년 테크 리드 논의"],
     "discussion": "MSA 전환과 DB 최적화 모두 목표 이상 달성. 팀 기술 역량 전체를 한 단계 높였다는 평가. 내년 테크 리드 후보로 검토 중.",
     "action_items": ["테크 리드 역할 준비 계획 수립"],
     "manager_feedback": "올해 팀 내 최고 기여자. A 등급 확정, 내년 테크 리드 적극 검토."}
]

# ─────────────────────────────────────────────
# 4. 본인평가 및 성장플랜 (self_reviews.json)
# ─────────────────────────────────────────────
self_reviews = [
    {
        "emp_id": "E001",
        "year": 2025,
        "self_grade": "B+",    # 본인이 예상하는 등급
        "achievement_summary": "추천 모델 정확도를 NDCG 0.748까지 향상시켰으며, API P95 레이턴시를 178ms로 개선했습니다. 박지훈 온보딩 멘토링을 성공적으로 완료했습니다.",
        "strength": "데이터 기반 의사결정, 체계적인 실험 설계, 기술 문제 해결 능력",
        "improvement_area": "코드 리뷰 참여 빈도를 더 높이고, 팀 내 기술 공유 활동 확대 필요",
        "growth_plan": "내년에는 ML 시스템 설계 역량을 강화하고, 오픈소스 기여를 통해 외부 기술 네트워크 구축 목표",
        "mutual_reflection": {
            "manager_support": "팀장님의 실험 방향성 피드백이 모델 개선에 큰 도움이 되었습니다.",
            "team_contribution": "박지훈 멘토링과 코드 리뷰를 통해 팀 전반의 코드 품질 향상에 기여했습니다.",
            "challenges": "레이턴시 최적화 초반에 원인 파악에 시간이 걸렸습니다. 다음에는 프로파일링을 더 일찍 시작하겠습니다."
        }
    },
    {
        "emp_id": "E002",
        "year": 2025,
        "self_grade": "S",
        "achievement_summary": "실시간 파이프라인 일 1.5M 이벤트 처리, 테스트 커버리지 87% 달성 등 모든 KPI를 초과 달성했습니다.",
        "strength": "기술적 실행력, 복잡한 시스템 설계 및 구현, 높은 코드 품질",
        "improvement_area": "팀 내 커뮤니케이션 방식 개선 노력 중. 코드 리뷰 코멘트 톤을 보다 건설적으로 조정하겠습니다.",
        "growth_plan": "내년에는 기술 역량 유지와 함께 팀 내 리더십 스킬 개발에 집중. 주니어 육성 프로그램 참여 계획.",
        "mutual_reflection": {
            "manager_support": "팀장님의 협업 이슈 피드백은 개선이 필요한 부분임을 인식하고 있습니다.",
            "team_contribution": "파이프라인 구축으로 팀 전체 개발 생산성이 크게 향상되었습니다.",
            "challenges": "기술적 판단에서 빠른 결정을 선호하다 보니 팀 합의 과정이 부족했습니다."
        }
    },
    {
        "emp_id": "E003",
        "year": 2025,
        "self_grade": "B",
        "achievement_summary": "할당된 기능 개발을 대부분 완료했으며, 버그 수정 업무도 성실히 수행했습니다. 기술 교육 2개를 수료했습니다.",
        "strength": "성실함, 빠른 학습 능력, 세심한 테스트 작성",
        "improvement_area": "개발 속도 향상과 단위 테스트 커버리지 확대. 기술 교육 이수 목표 달성 필요.",
        "growth_plan": "내년에는 백엔드 API 개발 역량을 강화하고, React 심화 학습을 통해 풀스택 역량 확보 목표",
        "mutual_reflection": {
            "manager_support": "김민준 시니어의 코드 리뷰와 멘토링이 성장에 큰 도움이 되었습니다.",
            "team_contribution": "꼼꼼한 버그 수정으로 서비스 품질 유지에 기여했습니다.",
            "challenges": "Q1 이후 1on1이 진행되지 않아 방향 설정에 아쉬움이 있었습니다."
        }
    },
    {
        "emp_id": "E004",
        "year": 2025,
        "self_grade": "B",
        "achievement_summary": "Grafana 모니터링 대시보드를 목표(10개) 초과인 12개 지표로 구축했으며, 서비스 가용성 99.95%를 달성했습니다.",
        "strength": "시스템 안정성 관리, 모니터링 도구 활용, 체계적인 문서화",
        "improvement_area": "P1 인시던트 대응 시간(MTTR)을 목표 30분 이내로 줄이는 것이 과제입니다.",
        "growth_plan": "내년에는 카오스 엔지니어링 학습을 통해 사전 장애 대응 역량을 키우고 SRE 전문성 강화 계획",
        "mutual_reflection": {
            "manager_support": "팀장님의 온콜 운영 가이드가 초기 인시던트 대응에 많은 도움이 되었습니다.",
            "team_contribution": "팀 전체가 사용하는 모니터링 인프라를 구축하여 장애 감지 시간이 크게 단축되었습니다.",
            "challenges": "MTTR 목표 달성을 위한 진단 도구 숙련도 부족이 아쉽습니다."
        }
    },
    {
        "emp_id": "E005",
        "year": 2025,
        "self_grade": "A",
        "achievement_summary": "4개 서비스 MSA 전환(목표 3개 초과)과 DB 슬로우 쿼리 92% 개선을 달성했습니다. 팀 전체 아키텍처 역량 향상에 기여했습니다.",
        "strength": "시스템 아키텍처 설계, 복잡한 기술 문제 해결, 팀 기술 방향 리딩",
        "improvement_area": "아키텍처 결정 내용을 더 체계적으로 문서화하여 팀 전체가 참고할 수 있도록 개선 필요",
        "growth_plan": "내년에는 테크 리드로서의 역할을 준비하고, 외부 컨퍼런스 발표를 통해 기술 브랜딩 강화 계획",
        "mutual_reflection": {
            "manager_support": "팀장님의 MSA 전환 프로젝트 지원과 신뢰가 도전적인 목표 달성의 원동력이 되었습니다.",
            "team_contribution": "MSA 전환으로 팀 배포 주기가 2배 빨라지고 장애 격리가 가능해졌습니다.",
            "challenges": "전환 초반 일부 서비스에서 예상치 못한 의존성 문제가 있었으나 팀과 협력하여 해결했습니다."
        }
    }
]

# ─────────────────────────────────────────────
# 5. 과거 평가 이력 (eval_history.json) - 2024년
# ─────────────────────────────────────────────
eval_history = [
    {
        "emp_id": "E001",
        "year": 2024,
        "grade": "B+",
        "achievement_grade": "A",       # 업적 등급
        "competency_grade": "B",        # 역량 등급
        "rank_in_team": 2,              # 팀 내 순위
        "manager_comment": "추천 시스템 개발에서 의미 있는 성과를 냈으며, 팀 내 기술 멘토 역할을 잘 수행했습니다. 내년에는 더 넓은 기술 영향력 발휘를 기대합니다.",
        "strength_keywords": ["기술 실행력", "멘토링", "체계적 실험"],
        "improvement_keywords": ["기술 공유", "문서화", "리더십"]
    },
    {
        # 엣지케이스: 2024년은 A 등급이었는데 2025년 S 등급 예정 - 급격한 상승
        "emp_id": "E002",
        "year": 2024,
        "grade": "A",
        "achievement_grade": "A+",
        "competency_grade": "B",
        "rank_in_team": 3,
        "manager_comment": "기술적 성과는 탁월하지만 팀 내 협업 방식에서 개선이 필요합니다. 기술과 소프트 스킬의 균형 있는 발전을 권장합니다.",
        "strength_keywords": ["기술 실행력", "데이터 처리", "테스트 설계"],
        "improvement_keywords": ["협업", "커뮤니케이션", "팀워크"]
    },
    {
        "emp_id": "E003",
        "year": 2024,
        "grade": "B",
        "achievement_grade": "B",
        "competency_grade": "B+",
        "rank_in_team": 5,
        "manager_comment": "성실하게 주어진 업무를 수행했으며, 빠른 성장세를 보이고 있습니다. 내년에는 더 도전적인 과제에 적극적으로 참여하기를 기대합니다.",
        "strength_keywords": ["성실함", "학습 의지", "버그 수정"],
        "improvement_keywords": ["개발 속도", "자기 주도성", "기술 깊이"]
    },
    {
        "emp_id": "E004",
        "year": 2024,
        "grade": "B",
        "achievement_grade": "B+",
        "competency_grade": "B-",
        "rank_in_team": 4,
        "manager_comment": "모니터링 시스템 도입에서 팀에 실질적 기여를 했습니다. 인시던트 대응 능력을 강화하면 SRE 전문가로 성장할 수 있습니다.",
        "strength_keywords": ["시스템 안정성", "문서화", "꼼꼼함"],
        "improvement_keywords": ["인시던트 대응", "장애 진단", "자동화"]
    },
    {
        "emp_id": "E005",
        "year": 2024,
        "grade": "A+",
        "achievement_grade": "A+",
        "competency_grade": "A",
        "rank_in_team": 1,
        "manager_comment": "팀 내 아키텍처 방향을 이끌며 높은 기술 수준과 리더십을 발휘했습니다. 내년에는 테크 리드로서의 역할 확대를 고려하고 있습니다.",
        "strength_keywords": ["아키텍처 설계", "기술 리더십", "문제 해결"],
        "improvement_keywords": ["문서화", "지식 공유", "위임 능력"]
    }
]

# ─────────────────────────────────────────────
# 6. HR DataLake (hr_datalake.json) - 메일·Teams·캘린더 요약
# ─────────────────────────────────────────────
hr_datalake = [
    {
        "emp_id": "E001",
        "year": 2025,
        "mail_summaries": [
            {"month": "2025-02", "subject": "[완료] 추천 모델 v2.1 배포", "summary": "추천 모델 v2.1 프로덕션 배포 완료. A/B 테스트 결과 CTR 8% 향상 확인."},
            {"month": "2025-05", "subject": "[공유] API 레이턴시 최적화 결과", "summary": "캐싱 레이어 도입으로 P95 레이턴시 230ms → 198ms 개선. 설계 문서 팀 공유."},
            {"month": "2025-08", "subject": "[완료] 박지훈 온보딩 멘토링 완료", "summary": "3개월 멘토링 완료. 박지훈 단위테스트 작성 역량 향상 확인. 종료 보고서 제출."},
            {"month": "2025-10", "subject": "[제안] 모델 서빙 아키텍처 개선안", "summary": "TorchServe 도입 제안. 벤치마크 결과 포함. 팀 리뷰 요청."}
        ],
        "teams_chats": [
            {"month": "2025-03", "context": "스프린트 회의", "summary": "모델 실험 결과 공유. 팀원들에게 피처 엔지니어링 방향 설명. 긍정적 반응."},
            {"month": "2025-06", "context": "기술 리뷰", "summary": "API 최적화 접근법 발표. 정우성과 캐싱 전략 논의. 합의점 도출."},
            {"month": "2025-09", "context": "팀 회의", "summary": "Q3 성과 공유. 아키텍처 개선 참여 의사 표명. 정우성 프로젝트 서포트 제안."}
        ],
        "calendar_summaries": [
            {"quarter": "Q1", "meetings": ["모델 실험 리뷰 4회", "1on1 팀장", "스프린트 회의 6회", "코드 리뷰 세션 12회"]},
            {"quarter": "Q2", "meetings": ["API 최적화 기술 리뷰 2회", "1on1 팀장", "스프린트 회의 6회", "박지훈 멘토링 8회"]},
            {"quarter": "Q3", "meetings": ["모델 A/B 테스트 리뷰 3회", "1on1 팀장", "아키텍처 리뷰(정우성) 2회"]},
            {"quarter": "Q4", "meetings": ["연간 성과 발표", "1on1 팀장", "내년 목표 워크샵"]}
        ]
    },
    {
        "emp_id": "E002",
        "year": 2025,
        "mail_summaries": [
            {"month": "2025-04", "subject": "[완료] 실시간 데이터 파이프라인 v1.0 릴리즈", "summary": "Kafka 기반 파이프라인 배포. 일 처리량 1.5M 이벤트 달성. 기술 문서 작성 완료."},
            {"month": "2025-07", "subject": "[공유] 테스트 커버리지 개선 가이드", "summary": "팀 테스트 커버리지 80% → 87% 향상 방법론 공유. 모범 사례 문서 배포."},
            {"month": "2025-09", "subject": "[이슈] 코드 리뷰 문화 개선 제안", "summary": "코드 리뷰 가이드라인 재정비 제안. 건설적 피드백 방식으로 전환 요청 수신."}
        ],
        "teams_chats": [
            {"month": "2025-02", "context": "기술 논의", "summary": "파이프라인 아키텍처 결정. 다른 팀원 의견 반영 없이 단독 결정으로 팀 마찰 발생."},
            {"month": "2025-05", "context": "코드 리뷰", "summary": "PR 리뷰에서 강한 비판적 코멘트. 팀장에게 톤 조정 요청 받음."},
            {"month": "2025-10", "context": "스프린트 회의", "summary": "파이프라인 확장 계획 발표. 이번에는 팀원 의견 수렴 후 결정. 개선된 모습."}
        ],
        "calendar_summaries": [
            {"quarter": "Q1", "meetings": ["파이프라인 설계 리뷰 3회", "1on1 팀장", "팀 협업 이슈 논의"]},
            {"quarter": "Q2", "meetings": ["파이프라인 배포 리뷰", "1on1 팀장", "코드 리뷰 세션 15회"]},
            {"quarter": "Q3", "meetings": ["테스트 커버리지 리뷰", "1on1 팀장", "협업 개선 워크샵"]},
            {"quarter": "Q4", "meetings": ["연간 성과 발표", "1on1 팀장", "리더십 코칭 2회"]}
        ]
    },
    {
        "emp_id": "E003",
        "year": 2025,
        "mail_summaries": [
            {"month": "2025-02", "subject": "[완료] 온보딩 완료 보고", "summary": "개발 환경 세팅, 코드베이스 파악, 첫 PR 머지 완료."},
            {"month": "2025-06", "subject": "[공유] 버그 수정 현황 보고", "summary": "Q1~Q2 배정 버그 20건 중 18건 처리 완료. 2건 Q3 이월."}
        ],
        "teams_chats": [
            {"month": "2025-01", "context": "온보딩", "summary": "팀 소개 및 코드베이스 가이드. 김민준 멘토로 지정됨."},
            {"month": "2025-04", "context": "스프린트 회의", "summary": "기능 개발 진행 상황 공유. 예상보다 버그 수정에 시간 소요됨."}
        ],
        "calendar_summaries": [
            {"quarter": "Q1", "meetings": ["온보딩 세션 5회", "1on1 팀장", "멘토링(김민준) 8회", "기술 교육 2회"]},
            {"quarter": "Q2", "meetings": ["스프린트 회의 6회", "멘토링(김민준) 4회"]},
            {"quarter": "Q3", "meetings": ["스프린트 회의 6회", "기술 교육 1회 수료"]},
            {"quarter": "Q4", "meetings": ["스프린트 회의 6회", "연간 성과 발표"]}
        ]
    },
    {
        "emp_id": "E004",
        "year": 2025,
        "mail_summaries": [
            {"month": "2025-05", "subject": "[완료] Grafana 대시보드 v1.0 배포", "summary": "핵심 서비스 지표 8개 시각화 완료. 팀 전체 접근 권한 설정."},
            {"month": "2025-09", "subject": "[완료] Grafana 대시보드 v2.0 - 12개 지표", "summary": "목표 초과 달성. 알림 설정 및 런북 연동 완료."},
            {"month": "2025-11", "subject": "[보고] P1 인시던트 사후 분석", "summary": "MTTR 35분. 근본 원인 분석 및 재발 방지 대책 수립."}
        ],
        "teams_chats": [
            {"month": "2025-03", "context": "온콜 논의", "summary": "온콜 로테이션 일정 조정. 인시던트 대응 프로세스 논의."},
            {"month": "2025-07", "context": "모니터링 리뷰", "summary": "대시보드 신규 지표 추가 논의. 팀원들 요청사항 수렴."},
            {"month": "2025-10", "context": "인시던트 리뷰", "summary": "P1 대응 회고. 진단 시간 단축 방법 논의. 런북 업데이트 합의."}
        ],
        "calendar_summaries": [
            {"quarter": "Q1", "meetings": ["모니터링 기획 리뷰 2회", "1on1 팀장", "온콜 온보딩 3회"]},
            {"quarter": "Q2", "meetings": ["대시보드 데모", "1on1 팀장", "인시던트 드릴 2회"]},
            {"quarter": "Q3", "meetings": ["대시보드 v2 리뷰", "1on1 팀장", "인시던트 리뷰 2회"]},
            {"quarter": "Q4", "meetings": ["연간 성과 발표", "1on1 팀장", "카오스 엔지니어링 세미나"]}
        ]
    },
    {
        "emp_id": "E005",
        "year": 2025,
        "mail_summaries": [
            {"month": "2025-03", "subject": "[완료] MSA 전환 로드맵 v1.0 공유", "summary": "4개 서비스 MSA 전환 계획. 분기별 마일스톤 포함. 팀장 승인 완료."},
            {"month": "2025-06", "subject": "[완료] 인증/결제 서비스 MSA 전환", "summary": "2개 서비스 전환 완료. 배포 자동화 파이프라인 구축. 롤백 프로세스 문서화."},
            {"month": "2025-10", "subject": "[완료] 4개 서비스 MSA 전환 완료", "summary": "목표(3개) 초과 달성. 시스템 전체 안정성 향상. DB 최적화 92% 달성."}
        ],
        "teams_chats": [
            {"month": "2025-02", "context": "아키텍처 리뷰", "summary": "MSA 전환 방향 발표. 팀 전체 동의. Q1 아키텍처 리뷰 세션 계획."},
            {"month": "2025-05", "context": "기술 리뷰", "summary": "전환 중 발생한 서비스 간 의존성 문제 해결 방안 공유. 팀원 학습 기회."},
            {"month": "2025-09", "context": "팀 회의", "summary": "MSA 전환 완료 발표. DB 최적화 성과 공유. 팀장 테크 리드 가능성 언급."}
        ],
        "calendar_summaries": [
            {"quarter": "Q1", "meetings": ["아키텍처 리뷰 세션(주도)", "1on1 팀장", "MSA 전환 킥오프"]},
            {"quarter": "Q2", "meetings": ["서비스 전환 리뷰 3회", "1on1 팀장", "DB 최적화 리뷰 2회", "아키텍처 리뷰 세션(주도)"]},
            {"quarter": "Q3", "meetings": ["MSA 전환 완료 리뷰", "1on1 팀장", "아키텍처 리뷰 세션(주도) 2회"]},
            {"quarter": "Q4", "meetings": ["연간 성과 발표", "1on1 팀장", "아키텍처 리뷰 세션(주도)", "테크 리드 사전 논의"]}
        ]
    }
]


def save_json(data: list | dict, filename: str) -> None:
    """JSON 파일로 저장하고 완료 메시지를 출력합니다."""
    filepath = MOCK_DATA_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [OK] {filepath} ({len(data) if isinstance(data, list) else 1} 건)")


if __name__ == "__main__":
    print("=" * 50)
    print("HR Mock Data 생성 시작")
    print("=" * 50)

    save_json(employees,          "employees.json")
    save_json(kpi_plans,          "kpi_plans.json")
    save_json(one_on_one_records, "1on1_records.json")
    save_json(self_reviews,       "self_reviews.json")
    save_json(eval_history,       "eval_history.json")
    save_json(hr_datalake,        "hr_datalake.json")

    print("=" * 50)
    print("완료! data/mock/ 디렉토리를 확인하세요.")
    print("다음 단계: python init_rag.py")
    print("=" * 50)
