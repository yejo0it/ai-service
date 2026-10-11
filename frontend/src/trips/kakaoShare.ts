/**
 * 카카오톡 공유 (Kakao JavaScript SDK).
 * VITE_KAKAO_JS_KEY가 없으면 쓰지 않는다(초대 화면은 링크 복사만 안내한다).
 * 카카오 개발자 콘솔의 플랫폼 > Web > 사이트 도메인에 서비스 주소를 등록해야 링크가 열린다.
 */

const KAKAO_JS_KEY = import.meta.env.VITE_KAKAO_JS_KEY ?? "";
const SDK_URL = "https://t1.kakaocdn.net/kakao_js_sdk/2.7.4/kakao.min.js";

interface KakaoLink {
  webUrl: string;
  mobileWebUrl: string;
}

interface KakaoSdk {
  isInitialized: () => boolean;
  init: (key: string) => void;
  Share: {
    sendDefault: (template: { objectType: "text"; text: string; link: KakaoLink; buttonTitle?: string }) => void;
  };
}

declare global {
  interface Window {
    Kakao?: KakaoSdk;
  }
}

export const isKakaoShareConfigured = () => KAKAO_JS_KEY !== "";

let loading: Promise<KakaoSdk> | null = null;

/** SDK를 한 번만 불러와 초기화한다. */
function loadKakao(): Promise<KakaoSdk> {
  if (!loading) {
    loading = new Promise<KakaoSdk>((resolve, reject) => {
      const ready = () => {
        const kakao = window.Kakao;
        if (!kakao) {
          reject(new Error("카카오톡 공유를 불러오지 못했어요."));
          return;
        }
        if (!kakao.isInitialized()) kakao.init(KAKAO_JS_KEY);
        resolve(kakao);
      };
      if (window.Kakao) {
        ready();
        return;
      }
      const script = document.createElement("script");
      script.src = SDK_URL;
      script.async = true;
      script.crossOrigin = "anonymous";
      script.onload = ready;
      script.onerror = () => reject(new Error("카카오톡 공유를 불러오지 못했어요."));
      document.head.appendChild(script);
    }).catch((err: unknown) => {
      loading = null;
      throw err;
    });
  }
  return loading;
}

/** 텍스트 메시지(최대 200자) + 링크 버튼으로 카카오톡 공유 창을 연다. */
export async function shareToKakao({ text, url, buttonTitle }: { text: string; url: string; buttonTitle: string }) {
  const kakao = await loadKakao();
  kakao.Share.sendDefault({
    objectType: "text",
    text: text.slice(0, 200),
    link: { webUrl: url, mobileWebUrl: url },
    buttonTitle,
  });
}
