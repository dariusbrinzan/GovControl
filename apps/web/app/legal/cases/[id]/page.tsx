import { EntityDetail } from "../../../../components/legal/entity-detail";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <EntityDetail entity="case" id={id} />; }
