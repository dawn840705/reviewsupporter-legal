#!/usr/bin/env python3
"""LinkPrice 리얼 핫딜 API → affiliate.json 하이브리드 생성.

구조(하이브리드, 2026-06-28):
  affiliate.json = [수동 고정 오퍼(manual_offers.json)] + [핫딜 API 자동 오퍼]
  - 수동 고정 = 식품(컬리·CJ) 등 커미션·궁합 좋은 큐레이션. **항상 상단 고정**.
  - 자동 = LinkPrice 리얼 핫딜 API의 MD 큐레이션 상품(딥링크 click_url 완비). 고정 아래로 채움.
  => 오퍼월/스크래핑 불필요. 공식 API라 약관 클린·머천트 패턴 LinkPrice가 관리.

핫딜 API(공식):
  GET https://api.linkprice.com/ci/hotdeal/data/{a_id}
  → [{merchant_id, product_code, product_name, category, product_image, click_url(완성 딥링크),
      promotional_text, commission_rate, ...}]  (30분마다 갱신, 종료 상품은 예고없이 제거)
  ⚠️ commission_rate는 '우리 수익'이지 유저 적립이 아님 → 카드에 노출 안 함(적립 동선 분리).

품질 필터:
  - click_url 기준 dedup(핫딜은 동일 상품을 카테고리별로 중복 반환)
  - SKU 코드형 상품명(한글·공백 없는 코드, 예 'DRB00087') 제외
  - 모바일 부적합 머천트(gmarket=모바일 수익 0 등) 블록

안전장치:
  - 핫딜 호출 실패/에러/0건 → 자동 오퍼 없이 고정 오퍼만 출력(식품 보존)
  - 고정·자동 둘 다 0 → no-op(기존 affiliate.json 보존)

규약 근거: ReviewSupporter/reports/어필리에이트_머천트_규약_종합_LinkPrice20_20260624.md
"""
import json
import os
import sys
import urllib.request

A_ID = "A100705176"          # 우리 LinkPrice 어필리에이트 코드
HOTDEAL = "https://api.linkprice.com/ci/hotdeal/data/%s" % A_ID
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "affiliate.json")
MANUAL = os.path.join(ROOT, "manual_offers.json")
MAX_OFFERS = 10              # AffiliateSection 코드 상한과 일치(고정+자동 합산)
TIMEOUT = 20

# "실적 미인정/모바일 수익 0" 머천트는 클릭돼도 수익 0 → 오퍼에서 제외.
# (근거=어필리에이트_머천트_규약_종합_LinkPrice20)
APP_BLOCKLIST = {
    "gmarket",     # 광고효과 0일 + 모바일 앱 수익 0 → 제외.
    # ★ APP 실적 미인정(2026-06-28 웹조사 — 머천트 상세 '실적인정범위' 표): 앱 클릭은 커미션 0이라 노출 무의미.
    "wconcept",    # APP(AOS/iOS) 미인정
    "kbbook",      # 교보문고 — APP 미인정
}
# 참고(APP 인정 머천트): himart(쿠키0일), cjbrand(CJ더마켓·쿠키30일=앱 최적), kurly(컬리·딥링크불가→메인링크만).
#   → APP 인정 식품(CJ·컬리)은 manual_offers.json 고정으로 운영(핫딜 피드는 미인정 머천트 위주라 자동만으론 수익 X).


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "rs-affiliate-bot/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def load_manual():
    """수동 고정 오퍼 로드. 없거나 깨지면 빈 목록(자동만으로 진행)."""
    try:
        with open(MANUAL, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("[info] manual_offers.json 없음 → 고정 오퍼 0")
        return []
    except Exception as e:
        print("[warn] manual_offers.json 파싱 실패: %s → 고정 오퍼 0" % e, file=sys.stderr)
        return []
    raw = data.get("offers") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    offers = []
    for o in raw:
        if not isinstance(o, dict):
            continue
        title = (o.get("title") or "").strip()
        url = o.get("url") or ""
        if not title or not isinstance(url, str) or not url.startswith("http"):
            continue
        offers.append(o)
    return offers


def is_junk_name(name):
    """SKU 코드형 상품명(한글·공백 없는 영문숫자 코드, 예 'DRB00087') = 광고로 부적합 → 제외."""
    if len(name) < 4:
        return True
    has_korean = any("가" <= c <= "힣" for c in name)
    has_space = " " in name
    return not has_korean and not has_space


def fetch_hotdeal():
    """핫딜 상품 목록. 실패/에러(dict)/리스트 아님이면 빈 목록(자동 생략)."""
    try:
        data = fetch(HOTDEAL)
    except Exception as e:
        print("[info] 핫딜 API 호출 실패: %s → 자동 오퍼 생략" % e)
        return []
    if isinstance(data, dict):  # 에러 응답 {"error-message": ...}
        print("[info] 핫딜 API 에러: %s → 자동 오퍼 생략" % data.get("error-message"))
        return []
    if not isinstance(data, list):
        return []
    return data


def build_auto_offers(products, slots):
    """핫딜 상품 → 자동 오퍼. dedup·정크명·블록 필터, 최대 slots개."""
    offers = []
    if slots <= 0:
        return offers
    seen_url = set()
    for p in products:
        if not isinstance(p, dict):
            continue
        mid = (p.get("merchant_id") or "").strip()
        if not mid or mid in APP_BLOCKLIST:
            continue
        click = p.get("click_url") or ""
        name = (p.get("product_name") or "").strip()
        if not isinstance(click, str) or not click.startswith("http") or not name:
            continue
        if click in seen_url or is_junk_name(name):
            continue
        # 이미지 없는 오퍼는 제외(형 요청 — 회색박스 광고 안 띄움).
        img = p.get("product_image") or ""
        if not (isinstance(img, str) and img.startswith("http")):
            continue
        seen_url.add(click)
        # subtitle(표시)은 생략 — category가 머천트 기준이라 상품과 어긋남(예: wconcept 냉동볶음밥에 '패션·뷰티').
        # 단 category는 별도 필드로 실어 보낸다 → 앱 온디바이스 맞춤정렬에 사용(표시 X, 정렬 O).
        offer = {
            "id": "lp-%s-%s" % (mid, (p.get("product_code") or len(offers))),
            "title": name,
            "url": click,
            "merchant": mid,
            "imageUrl": img,
        }
        cat = (p.get("category") or "").strip()
        if cat:
            offer["category"] = cat
        offers.append(offer)
        if len(offers) >= slots:
            break
    return offers


def main():
    pinned = load_manual()
    products = fetch_hotdeal()
    auto = build_auto_offers(products, MAX_OFFERS - len(pinned))

    merged = (pinned + auto)[:MAX_OFFERS]
    if not merged:
        print("[skip] 고정·자동 오퍼 모두 0 → 기존 affiliate.json 보존")
        return 0

    out = {
        "_comment": (
            "AUTO-GENERATED by scripts/build_affiliate.py (하이브리드: manual_offers.json 고정 + "
            "LinkPrice 리얼 핫딜 API 자동, cron). ★직접 편집 금지 — 수동 오퍼는 manual_offers.json을 "
            "수정. 머천트 필터 근거=ReviewSupporter/reports/어필리에이트_머천트_규약_종합_LinkPrice20_20260624.md"
        ),
        "offers": merged,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("[ok] 고정 %d + 자동 %d = %d개: %s" % (
        len(pinned), len(auto), len(merged),
        ", ".join(o.get("merchant", "?") for o in merged),
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
