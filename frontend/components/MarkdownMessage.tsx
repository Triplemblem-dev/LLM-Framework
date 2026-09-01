"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      components={{
        a: ({ href, children }) => {
          const external = href?.startsWith("http://") || href?.startsWith("https://");
          return (
            <a
              href={href}
              target={external ? "_blank" : undefined}
              rel={external ? "noreferrer noopener" : undefined}
            >
              {children}
            </a>
          );
        },
        img: ({ alt }) => (
          <span className="markdown-image-omitted">
            {alt ? `Image omitted: ${alt}` : "Remote image omitted"}
          </span>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
