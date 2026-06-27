#!/usr/bin/env python3
"""LinkPrice 오퍼월(쇼핑적립) API → affiliate.json 하이브리드 생성.

구조(하이브리드, 2026-06-28):
  affiliate.json = [수동 고정 오퍼(manual_offers.json)] + [오퍼월 자동 오퍼]
  - 수동 고정 = 식품(컬리·CJ) 등 커미션·궁합 좋은 큐레이션. **항상 상단 고정**.
  - 오퍼월 자동 = 종합몰(11번가·알리 등). 고정 오퍼 아래로 채움(머천트 중복 제거, 총 10개 상한).
  => 오퍼월을 켜도 수동 식품 오퍼가 절대 사라지지 않는다(이전엔 통째로 덮어써 식품이 날아갔음).

동작:
  1. manual_offers.json 로드(고정 오퍼). 편집 지점은 여기 — affiliate.json은 자동 생성물.
  2. 오퍼월 메인 호출로 머천트 목록(offerwall_cards) 획득
  3. 머천트별 상세 호출로 click_url(실제 제휴 딥링크) 획득
  4. 모바일 부적합 머천트(PC전용 등)·고정과 중복 머천트 필터
  5. 고정 + 자동 병합해 affiliate.json 덮어쓰기

안전장치(가장 중요):
  - 오퍼월 미설정(code != 0, 예: -6) / 호출 실패 / 머천트 0 → 자동 오퍼 없이 진행(고정 오퍼만 출력)
  - 고정 + 자동 둘 다 0 → no-op(기존 affiliate.json 보존)
  => 오퍼월이 켜지기 전까지는 고정 오퍼(컬리·CJ)가 그대로 유지된다.

규약 근거: ReviewSupporter/reports/어필리에이트_머천트_규약_종합_LinkPrice20_20260624.md
"""
import json
import os
import sys
import urllib.parse
import urllib.request

A_ID = "A100705176"          # 우리 LinkPrice 어필리에이트 코드
U_ID = "rs_auto"             # 익명 고정(무리워드 모델 — 유저별 적립 안 줌)
BASE = "https://api.linkprice.com/offerwall"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "affiliate.json")
MANUAL = os.path.join(ROOT, "manual_offers.json")
MAX_OFFERS = 10              # AffiliateSection 코드 상한과 일치(고정+자동 합산)
TIMEOUT = 20

# 우리 앱은 Linking.openURL로 모바일웹/머천트앱을 연다.
# "실적 미인정" 머천트는 클릭돼도 수익 0 → 오퍼에서 제외.
# (근거=어필리에이트_머천트_규약_종합_LinkPrice20)
APP_BLOCKLIST = {
    "gmarket",   # PC만 인정 → 모바일 앱 수익 0
}
# 참고(유지하되 주의): hmall=iOS미인정, lotteon/yes24/kbbook=앱미인정이나
# 모바일웹 fallback 시 인정 가능 → 블록하지 않음. 손실 보이면 위 set에 추가.


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


def fetch_offerwall_cards():
    """오퍼월 머천트 카드 목록. 미설정/실패/0이면 빈 목록(자동 오퍼 없이 진행)."""
    main_url = "%s/%s?%s" % (
        BASE, A_ID, urllib.parse.urlencode({"mode": "json", "u_id": U_ID})
    )
    try:
        data = fetch(main_url)
    except Exception as e:
        print("[info] 오퍼월 호출 실패: %s → 자동 오퍼 생략" % e)
        return []
    code = data.get("code") if isinstance(data, dict) else None
    if code is not None and code != 0:
        print("[info] 오퍼월 미설정 (code=%s, msg=%s) → 자동 오퍼 생략" % (code, data.get("msg")))
        return []
    cards = (data.get("offerwall_cards") or []) if isinstance(data, dict) else []
    if not cards:
        print("[info] 오퍼월 머천트 0 → 자동 오퍼 생략")
    return cards


def build_auto_offers(cards, pinned_merchants, slots):
    """오퍼월 카드 → 자동 오퍼. 블록·고정중복 제외, 최대 slots개."""
    offers = []
    if slots <= 0:
        return offers
    seen = set()
    for c in cards:
        mid = c.get("merchant_id")
        if not mid or mid in APP_BLOCKLIST or mid in pinned_merchants or mid in seen:
            continue
        det_url = "%s/%s/detail?%s" % (
            BASE, A_ID,
            urllib.parse.urlencode({"mode": "json", "u_id": U_ID, "m_id": mid}),
        )
        try:
            det = fetch(det_url)
        except Exception as e:
            print("[warn] %s 상세 호출 실패: %s" % (mid, e), file=sys.stderr)
            continue
        click = det.get("click_url")
        if not click or not click.startswith("http"):
            print("[warn] %s click_url 없음 → 제외" % mid, file=sys.stderr)
            continue
        seen.add(mid)
        name = (c.get("site_name") or mid).strip()
        comm = (c.get("max_commission") or "").strip()
        offer = {
            "id": "lp-%s" % mid,
            "title": name,
            "subtitle": ("최대 적립 %s" % comm) if comm else "쇼핑적립",
            "url": click,
            "merchant": mid,
        }
        banner = c.get("banner_url")
        if banner and banner.startswith("http"):
            offer["imageUrl"] = banner
        offers.append(offer)
        if len(offers) >= slots:
            break
    return offers


def main():
    pinned = load_manual()
    pinned_merchants = {o.get("merchant") for o in pinned if o.get("merchant")}

    cards = fetch_offerwall_cards()
    auto = build_auto_offers(cards, pinned_merchants, MAX_OFFERS - len(pinned))

    merged = (pinned + auto)[:MAX_OFFERS]
    if not merged:
        print("[skip] 고정·자동 오퍼 모두 0 → 기존 affiliate.json 보존")
        return 0

    out = {
        "_comment": (
            "AUTO-GENERATED by scripts/build_affiliate.py (하이브리드: manual_offers.json 고정 + "
            "LinkPrice 오퍼월 자동, 하루 1회). ★직접 편집 금지 — 수동 오퍼는 manual_offers.json을 "
            "수정. 머천트 필터 근거=ReviewSupporter/reports/어필리에이트_머천트_규약_종합_LinkPrice20_20260624.md"
        ),
        "offers": merged,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("[ok] 고정 %d + 자동 %d = %d개 오퍼: %s" % (
        len(pinned), len(auto), len(merged),
        ", ".join(o.get("merchant", "?") for o in merged),
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
