import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Steam Character Finder",
  description: "기분, 관계, 분위기로 고르는 게임",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="ko">
      <body>
        {children}
      </body>
    </html>
  );
}