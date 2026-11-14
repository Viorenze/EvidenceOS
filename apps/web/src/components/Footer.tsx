import * as React from "react";
import * as stylex from "@stylexjs/stylex";
import { colors, spacing } from "../styles/tokens.stylex";

const styles = stylex.create({
  footer: {
    borderTopWidth: 1,
    borderTopStyle: "solid",
    borderTopColor: colors.borderSubtle,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    paddingLeft: spacing.lg,
    paddingRight: spacing.lg,
    textAlign: "center",
    backgroundColor: colors.bgCard,
    marginTop: "auto",
  },
  text: {
    fontSize: "0.75rem",
    color: colors.textMuted,
    lineHeight: 1.5,
  },
});

export function Footer() {
  return (
    <footer {...stylex.props(styles.footer)}>
      <p {...stylex.props(styles.text)}>EvidenceOS · 真实运行核对 · 服务端引用校验 · 无编造保真</p>
    </footer>
  );
}
