import type { PackageVideo } from "../../api/types";
import VideoPlayer from "./VideoPlayer";
import LoadingSpinner from "../layout/LoadingSpinner";

interface VideoListProps {
  videos: PackageVideo[];
}

export default function VideoList({ videos }: VideoListProps) {
  if (videos.length === 0) {
    return <LoadingSpinner size="sm" label="Planning scenes…" />;
  }

  return (
    <div className="flex flex-col gap-6">
      {videos.map((video) => (
        <div
          key={video.scene_name}
          className="rounded-lg border border-border bg-surface p-4"
        >
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h4 className="font-semibold text-text-primary">{video.scene_name}</h4>
            <div className="flex items-center gap-2">
              {video.folder && (
                <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
                  {video.folder}
                </span>
              )}
              {video.is_overview && (
                <span className="rounded-full bg-accent/15 px-2 py-0.5 text-xs text-accent">
                  overview
                </span>
              )}
            </div>
          </div>

          {video.status === "done" && video.video_url ? (
            <>
              <VideoPlayer url={video.video_url} />
              <a
                href={video.video_url}
                download
                className="mt-3 inline-block text-sm text-accent hover:underline"
              >
                Download video →
              </a>
            </>
          ) : video.status === "error" ? (
            <p className="text-sm text-error">Rendering failed for this scene.</p>
          ) : (
            <LoadingSpinner size="sm" label="Rendering…" />
          )}
        </div>
      ))}
    </div>
  );
}
