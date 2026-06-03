---
name: curate-trends
description: 최신 반도체 산업 동향을 수집해 트렌드 도메인 콘텐츠를 갱신한다. HBM/EUV/GAA/첨단패키징 로드맵 수집, 트렌드 질문·모범답안 갱신, stale 정보 교체. "동향 수집", "트렌드 갱신", "최신 반도체 뉴스", "stale 콘텐츠 점검" 요청 시 사용. 산업 동향 운영 작업이면 반드시 이 스킬을 쓴다.
---

# 산업 동향 큐레이션

trend-curator 에이전트가 최신 반도체 동향을 수집해 트렌드 콘텐츠를 갱신하는 절차.

## 왜 필요한가

LLM 학습 cutoff 이후 정보(HBM 세대, High-NA EUV, GAA/CFET 양산 시점, 첨단 패키징)는
모범답안에서 stale해지기 쉽다. 이 제품이 "교수의 2~3년 lag"를 메우는 차별점이므로
트렌드 도메인의 최신성이 핵심이다.

## 워크플로우

### 1. 토픽 선정
주력 트렌드 축: HBM(HBM3E/HBM4), EUV/High-NA, GAA·CFET 로드맵, 첨단 패키징
(CoWoS/SoIC/하이브리드 본딩), 파운드리 노드(N2/A16 등), 3D NAND 단수.

### 2. 최신 수집 (연도 명시)
WebSearch 시 **현재 연도를 쿼리에 넣어** stale article을 피한다(제품의
`IndustrySearchService` 전략과 동일). 예: "2026 HBM4 mass production roadmap".
필요하면 WebFetch로 1차 출처를 확인한다.

### 3. 출처·날짜 병기
수집 항목마다 출처 URL·발행일을 남긴다. 상충 정보(양산 시점·세대)는 단일값으로 단정하지
말고 출처별로 병기한다.

### 4. 트렌드 질문으로 가공
면접관(산업 분석가 페르소나) 관점 — 양산성·수율·로드맵 함의로 정리하고,
question-bank-curator가 쓸 수 있는 트렌드 질문 후보 + key_points로 만든다.

예:
```
질문: "HBM4가 HBM3E 대비 갖는 구조적 변화와 컨트롤러 다이 통합(base die) 추세의
       의미를 설명하세요."
key_points:
  - 채널 수 2배(2048-bit) + 베이스 다이 로직 통합
  - 커스텀 HBM(파운드리 협업) 추세
  - 대역폭/전력효율 향상과 패키징 비용 트레이드오프
출처: <url> (YYYY-MM-DD)
```

### 5. 검수 게이트
트렌드 질문·모범답안은 `_workspace/trends_<날짜>.md`에 제안으로 쓰고, accuracy-reviewer의
정확성·최신성 검수를 통과한 뒤 question-bank-curator가 코드에 반영한다.

## 산출물

`_workspace/trends_<날짜>.md`:
- 토픽별 최신 동향(출처·날짜 병기)
- 트렌드 질문 후보 + key_points
- 교체 필요한 stale 콘텐츠 지목

## 원칙

- WebSearch 불가 → 미수집 보고. 기존 지식 추정은 "미검증"으로 분리(최신성 주장 금지).
- 뉴스 요약이 아니라 면접 평가에 쓸 양산·로드맵 관점으로 정리한다.
