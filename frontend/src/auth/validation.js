/** 로그인·가입·계정 찾기 공통 입력 규칙 (백엔드 accounts.serializers와 같은 규칙) */

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d\s])\S{8,20}$/;
export const PASSWORD_RULE = "영문, 숫자, 특수문자를 모두 포함해 8~20자";
export const PASSWORD_RULE_MESSAGE = `비밀번호는 ${PASSWORD_RULE}로 입력해 주세요.`;
export const PHONE_PATTERN = /^01[016789]\d{7,8}$/;

/** DRF 필드 에러 { field: [msg] } 에서 첫 메시지만 꺼낸다. */
export const firstError = (data, field) => {
  const value = data?.[field];
  return Array.isArray(value) ? value[0] : value;
};
