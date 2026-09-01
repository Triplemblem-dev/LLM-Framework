"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownMessageProps {
  content: string;
  suppressThematicBreaks?: boolean;
}

function tableCells(row: string): string[] {
  return row
    .trim()
    .replace(/^\|\s*/, "")
    .replace(/\s*\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function tableRow(cells: string[]): string {
  return `| ${cells.join(" | ")} |`;
}

export function normalizeAssistantMarkdown(content: string): string {
  const separatorPattern = /^:?-{3,}:?$/;
  const separatorCandidatePattern = /^:?-*:?$/;
  const normalizedLines = content
    .split("\n")
    .map((line) => {
      const candidate = line.trim();
      if (!candidate.startsWith("|") || !candidate.endsWith("|") || !candidate.includes("| |")) {
        return line;
      }

      const collapsedRows = candidate.split(/\|\s+\|/);
      if (collapsedRows.length < 3) return line;

      const [header, separator, ...dataRows] = collapsedRows.map(tableCells);
      if (!header || !separator) return line;

      const rows = [header, separator, ...dataRows];
      const columnCount = header.length;
      if (columnCount < 2 || rows.some((row) => row.length !== columnCount)) return line;

      if (!separator.some((cell) => separatorPattern.test(cell))) return line;

      const repairedSeparator = separator.map((cell) => (separatorPattern.test(cell) ? cell : "---"));
      return [header, repairedSeparator, ...dataRows].map(tableRow).join("\n");
    });

  return normalizedLines
    .map((line, index) => {
      if (index === 0) return line;

      const previous = normalizedLines[index - 1];
      if (!previous) return line;

      const headerLine = previous.trim();
      const separatorLine = line.trim();
      if (
        !headerLine.startsWith("|") ||
        !headerLine.endsWith("|") ||
        !separatorLine.startsWith("|") ||
        !separatorLine.endsWith("|")
      ) {
        return line;
      }

      const header = tableCells(headerLine);
      const separator = tableCells(separatorLine);
      if (
        header.length < 2 ||
        header.length !== separator.length ||
        !separator.some((cell) => separatorPattern.test(cell)) ||
        !separator.every((cell) => separatorCandidatePattern.test(cell))
      ) {
        return line;
      }

      const indentation = line.slice(0, line.length - line.trimStart().length);
      return indentation + tableRow(
        separator.map((cell) => (separatorPattern.test(cell) ? cell : "---"))
      );
    })
    .join("\n");
}

export function MarkdownMessage({ content, suppressThematicBreaks = false }: MarkdownMessageProps) {
  const renderedContent = suppressThematicBreaks ? normalizeAssistantMarkdown(content) : content;

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
        hr: () => (suppressThematicBreaks ? null : <hr />),
      }}
    >
      {renderedContent}
    </ReactMarkdown>
  );
}
