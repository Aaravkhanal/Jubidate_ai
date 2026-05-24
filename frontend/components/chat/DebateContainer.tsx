"use client";

import { useEffect, useRef } from "react";
import type { DebateMessage, SessionSettings } from "@/types";
import { UserMessageCard } from "./UserMessageCard";
import { AIMessageCard } from "./AIMessageCard";
import { JudgeMessageCard } from "./JudgeMessageCard";
import { DebateRoundHeader } from "./DebateRoundHeader";

type DebateContainerProps = {
  messages: DebateMessage[];
  partialMessages: Record<string, DebateMessage>;
  settings: SessionSettings | null;
};

export function DebateContainer({
  messages,
  partialMessages,
  settings
}: DebateContainerProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const partialList = Object.values(partialMessages);
  
  // Sort messages by sequence to ensure proper chronological flow
  const sortedMessages = [...messages].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));

  useEffect(() => {
    if (settings?.auto_scroll) {
      // Small timeout ensures the DOM has updated completely before scroll triggers
      const timer = setTimeout(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [messages, partialList.length, settings?.auto_scroll]);

  // We trace the last phase key to insert separators dynamically
  let lastPhaseKey: string | null = null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 px-4 py-6 w-full">
      {sortedMessages.map((message) => {
        const isUser = message.role === "user" || message.role === "practice_user";
        const isJudge =
          message.role === "judge" ||
          message.role === "judge_assistant" ||
          message.role === "judge_panelist" ||
          message.role === "debate_trainer";

        const showHeader = message.phase_title && message.phase_key !== lastPhaseKey;
        if (message.phase_key) {
          lastPhaseKey = message.phase_key;
        }

        return (
          <div key={message.id} className="flex flex-col gap-1 w-full">
            {showHeader && message.phase_title && (
              <DebateRoundHeader
                title={message.phase_title}
                subtitle={
                  message.phase_total
                    ? `Phase ${message.phase_index} of ${message.phase_total}`
                    : undefined
                }
              />
            )}
            {isUser ? (
              <UserMessageCard message={message} settings={settings} />
            ) : isJudge ? (
              <JudgeMessageCard message={message} settings={settings} />
            ) : (
              <AIMessageCard message={message} settings={settings} />
            )}
          </div>
        );
      })}

      {partialList.map((message) => {
        const isUser = message.role === "user" || message.role === "practice_user";
        const isJudge =
          message.role === "judge" ||
          message.role === "judge_assistant" ||
          message.role === "judge_panelist" ||
          message.role === "debate_trainer";

        return (
          <div key={message.id} className="flex flex-col gap-1 w-full">
            {isUser ? (
              <UserMessageCard message={message} settings={settings} pending />
            ) : isJudge ? (
              <JudgeMessageCard message={message} settings={settings} pending />
            ) : (
              <AIMessageCard message={message} settings={settings} pending />
            )}
          </div>
        );
      })}
      
      <div ref={bottomRef} className="h-2 w-full" />
    </div>
  );
}
