declare module "html-to-docx" {
  interface HtmlToDocxOptions {
    orientation?: "portrait" | "landscape";
    pageSize?: { width?: number; height?: number };
    margins?: Record<string, unknown>;
    title?: string;
    subject?: string;
    creator?: string;
    keywords?: string[];
    font?: string;
    fontSize?: number;
    lang?: string;
    footer?: boolean;
    pageNumber?: boolean;
    table?: { row?: { cantSplit?: boolean } };
    [key: string]: unknown;
  }

  export default function HTMLtoDOCX(
    htmlString: string,
    headerHTMLString?: string | null,
    documentOptions?: HtmlToDocxOptions,
    footerHTMLString?: string
  ): Promise<Buffer>;
}
