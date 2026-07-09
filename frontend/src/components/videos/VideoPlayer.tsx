import ReactPlayer from "react-player";

interface VideoPlayerProps {
  url: string;
}

export default function VideoPlayer({ url }: VideoPlayerProps) {
  return (
    <div className="aspect-video w-full overflow-hidden rounded-lg border border-border bg-black">
      <ReactPlayer url={url} controls width="100%" height="100%" />
    </div>
  );
}
