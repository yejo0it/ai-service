/** 로그인·가입·계정 찾기 공통 입력 규칙 (백엔드 accounts.serializers와 같은 규칙) */

import type { ApiErrorData } from "../types/api";

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d\s])\S{8,20}$/;
export const PASSWORD_RULE = "영문, 숫자, 특수문자를 모두 포함해 8~20자";
export const PASSWORD_RULE_MESSAGE = `비밀번호는 ${PASSWORD_RULE}로 입력해 주세요.`;
export const PHONE_PATTERN = /^01[016789]\d{7,8}$/;

/** DRF 필드 에러 { field: [msg] } 에서 첫 메시지만 꺼낸다. */
export const firstError = (data: ApiErrorData | undefined, field: string): string | undefined => {
  if (!data || typeof data === "string") return undefined;
  const value = data[field];
  if (Array.isArray(value)) return typeof value[0] === "string" ? value[0] : undefined;
  return typeof value === "string" ? value : undefined;
};

/** 백엔드 accounts.nickname과 같은 규칙 */
export const NICKNAME_PATTERN = /^(?=.{2,12}$)[가-힣A-Za-z0-9_]+(?: [가-힣A-Za-z0-9_]+)*$/;
const NICKNAME_RULE_MESSAGE = "닉네임은 한글, 영문, 숫자, 밑줄(_)로 2~12자 입력해 주세요.";
const NICKNAME_SPACING_MESSAGE = "단어 사이 공백은 한 칸만 허용합니다.";

/** 앞뒤 공백을 지운 닉네임의 형식 오류 메시지. 문제가 없으면 빈 문자열. 공백이 두 칸 이상이면 그 안내만 한다. */
export const nicknameError = (value: string) =>
  value.includes("  ") ? NICKNAME_SPACING_MESSAGE : NICKNAME_PATTERN.test(value) ? "" : NICKNAME_RULE_MESSAGE;
