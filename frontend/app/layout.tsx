export const metadata = {
  title: "C3 — Command Center",
  description: "Central Command & Control console (PoC)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
