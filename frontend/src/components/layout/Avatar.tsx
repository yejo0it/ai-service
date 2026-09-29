interface AvatarProps {
  name: string;
  /** 업로드한 프로필 이미지. 없으면 이름 첫 글자로 기본 아바타를 그린다. */
  src?: string | null;
  size?: number;
}

/** 원형 프로필 이미지 */
export default function Avatar({ name, src, size = 32 }: AvatarProps) {
  const style = { width: size, height: size };
  if (src) {
    return <img src={src} alt="" style={style} className="rounded-full object-cover ring-1 ring-slate-200" />;
  }
  return (
    <span
      aria-hidden="true"
      style={{ ...style, fontSize: size * 0.42 }}
      className="inline-flex items-center justify-center rounded-full bg-indigo-100 font-semibold text-indigo-700 ring-1 ring-indigo-200"
    >
      {name.trim().charAt(0).toUpperCase() || "P"}
    </span>
  );
}
