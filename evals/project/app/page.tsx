'use client';

import styles from "./page.module.css";
import { formatTitle } from "../lib/helpers";

export default function Page({ ok }: { ok: boolean }) {
  const state = ok ? "done" : "pending";
  return (
    <div className={styles.card}>
      <span className={styles[state]}>{formatTitle("eval")}</span>
    </div>
  );
}
