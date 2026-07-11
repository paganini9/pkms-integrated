/** 관리자 표면 — 골격 + 403 처리만 (T-62 우선순위 밖). 상세 구현은 후속. */
import { useApp } from "../store";
import { Card, Chip } from "../components/ui";

export default function AdminPlaceholder({ title, surface }: { title: string; surface: string }) {
  const role = useApp((s) => s.role);

  if (role !== "admin") {
    // CD-5: 비관리자는 403. error_model FORBIDDEN 의 user_message 를 사용.
    return (
      <Card title="접근 제한" tone="bad">
        <p className="text-sm text-rose-700">관리자 권한이 필요합니다.</p>
        <p className="mt-1 text-xs text-slate-500">상단바에서 역할을 관리자로 전환하면 골격을 볼 수 있습니다. (Mock-Role · CD-5)</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">{title}</h1>
        <p className="text-sm text-slate-500 mt-1">관리자 콘솔 골격입니다. 규칙·SHACL 은 문장 파생물이며 직접 편집 표면은 없습니다(생성 뷰·읽기 전용).</p>
      </div>
      <Card>
        <p className="text-sm text-slate-600">
          <Chip color="violet">{surface}</Chip> 표면은 admin 전용입니다(§4.8). Phase 2 우선순위는 T-60·62(엔지니어 핵심 루프)이며, 관리자 화면은 후속 구현 대상입니다.
        </p>
      </Card>
    </div>
  );
}
