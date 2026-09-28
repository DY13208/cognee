"use client";

import { useEffect, useState } from "react";

const LEFT_KEY = "cognee.teleology.leftOpen";
const RIGHT_KEY = "cognee.teleology.rightOpen";

function readOpen(key: string): boolean | null {
  try {
    const value = window.localStorage.getItem(key);
    if (value === "0") return false;
    if (value === "1") return true;
  } catch {
    /* ignore */
  }
  return null;
}

function writeOpen(key: string, open: boolean) {
  try {
    window.localStorage.setItem(key, open ? "1" : "0");
  } catch {
    /* ignore */
  }
}

/** Shared collapse state so both teleology views keep the same rails. */
export function useSideOpen() {
  const [leftOpen, setLeft] = useState(true);
  const [rightOpen, setRight] = useState(true);

  useEffect(() => {
    const left = readOpen(LEFT_KEY);
    const right = readOpen(RIGHT_KEY);
    if (left !== null) setLeft(left);
    if (right !== null) setRight(right);
  }, []);

  return {
    leftOpen,
    rightOpen,
    setLeftOpen: (open: boolean) => {
      setLeft(open);
      writeOpen(LEFT_KEY, open);
    },
    setRightOpen: (open: boolean) => {
      setRight(open);
      writeOpen(RIGHT_KEY, open);
    },
  };
}
