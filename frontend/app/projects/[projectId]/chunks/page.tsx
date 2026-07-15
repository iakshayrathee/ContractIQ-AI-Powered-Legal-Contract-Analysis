import ChunksPage from "@/components/chunks/ChunksPage";

interface Props {
  params: Promise<{ projectId: string }>;
}

export default async function Page({ params }: Props) {
  const { projectId } = await params;
  return <ChunksPage projectName={decodeURIComponent(projectId)} />;
}
