"use client";

import { Button, Icon } from "@/components/ui";

export function PrintButton() {
  return (
    <Button onClick={() => window.print()}>
      <Icon name="download" /> Print or save as PDF
    </Button>
  );
}
