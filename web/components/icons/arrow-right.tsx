import React from "react";

import type { Props } from "./types";

export const ArrowRightIcon: React.FC<Props> = ({
  width = "24",
  height = "24",
  color = "var(--color-neutral-110)",
  className,
}) => (
  <svg
    width={width}
    height={height}
    className={className}
    viewBox="0 0 16 10"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      d="M10.9583 0.500103L15.0625 4.58344C15.1319 4.65288 15.1806 4.72232 15.2083 4.79177C15.2361 4.86121 15.25 4.9376 15.25 5.02094C15.25 5.10427 15.2361 5.18066 15.2083 5.2501C15.1806 5.31955 15.1319 5.38899 15.0625 5.45844L10.9583 9.5626C10.8472 9.67371 10.7014 9.73274 10.5208 9.73969C10.3403 9.74663 10.1875 9.6876 10.0625 9.5626C9.9375 9.4376 9.875 9.2883 9.875 9.11469C9.875 8.94108 9.9375 8.79177 10.0625 8.66677L13.0833 5.64594L1.125 5.64594C0.944443 5.64594 0.795138 5.58691 0.677083 5.46885C0.559026 5.3508 0.5 5.20149 0.5 5.02094C0.5 4.84038 0.559026 4.69108 0.677083 4.57302C0.795138 4.45496 0.944443 4.39594 1.125 4.39594L13.0833 4.39594L10.0625 1.3751C9.95139 1.26399 9.89236 1.12163 9.88542 0.94802C9.87847 0.774409 9.9375 0.625103 10.0625 0.500103C10.1875 0.375103 10.3368 0.312602 10.5104 0.312602C10.684 0.312602 10.8333 0.375103 10.9583 0.500103Z"
      fill={color}
    />
  </svg>
);
