import { Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import AdminPlaceholder from "./screens/AdminPlaceholder";
import Dashboard from "./screens/Dashboard";
import DesignVerify from "./screens/DesignVerify";
import KnowledgeInput from "./screens/KnowledgeInput";
import KnowledgeMap from "./screens/KnowledgeMap";
import QA from "./screens/QA";
import Requirements from "./screens/Requirements";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="input" element={<KnowledgeInput />} />
        <Route path="requirements" element={<Requirements />} />
        <Route path="verify" element={<DesignVerify />} />
        <Route path="qa" element={<QA />} />
        <Route path="map" element={<KnowledgeMap />} />
        <Route path="admin/ontology" element={<AdminPlaceholder title="상위 온톨로지" surface="/upper-ontology" />} />
        <Route path="admin/rules" element={<AdminPlaceholder title="도메인 규칙 · SHACL" surface="/rules" />} />
        <Route path="admin/governance" element={<AdminPlaceholder title="거버넌스" surface="/governance" />} />
        <Route path="*" element={<Dashboard />} />
      </Route>
    </Routes>
  );
}
