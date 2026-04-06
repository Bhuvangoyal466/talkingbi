import { useState, useEffect } from "react";
import AppSidebar from "@/components/AppSidebar";
import TopNav from "@/components/TopNav";
import ChatView from "@/components/ChatView";
import ChartsView from "@/components/ChartsView";
import InsightsView from "@/components/InsightsView";
import { SessionProvider } from "@/hooks/use-session";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

const TAB_KEY = "talkingbi_active_tab";

// Maps quick-action IDs to natural language prompts sent to the chat
const QUICK_ACTION_PROMPTS: Record<string, string> = {
  "data-summary": "Give me a summary of the current dataset",
  "clean-data":   "Clean the data — remove duplicates, fix nulls, and standardise formats",
};

const Index = () => {
  const [activeTab, setActiveTab] = useState<string>(() => {
    return sessionStorage.getItem(TAB_KEY) ?? "chat";
  });
  const [quickMessage, setQuickMessage] = useState<string | undefined>(undefined);
  const [cmdOpen, setCmdOpen] = useState(false);

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    sessionStorage.setItem(TAB_KEY, tab);
  };

  const handleQuickAction = (action: string) => {
    if (action === "trend-chart") {
      handleTabChange("charts");
    } else if (action === "auto-insights") {
      handleTabChange("insights");
    } else if (action === "__goto_chat__") {
      handleTabChange("chat");
    } else {
      handleTabChange("chat");
      setQuickMessage(QUICK_ACTION_PROMPTS[action] ?? action);
    }
    setCmdOpen(false);
  };

  // Ctrl+K / Cmd+K shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setCmdOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <SessionProvider>
      <div className="flex h-screen overflow-hidden">
        <AppSidebar onQuickAction={handleQuickAction} activeTab={activeTab} />
        <div className="flex-1 flex flex-col min-w-0">
          <TopNav activeTab={activeTab} onTabChange={handleTabChange} />
          <main className="flex-1 overflow-hidden">
            {activeTab === "chat" && (
              <ChatView
                quickMessage={quickMessage}
                onQuickMessageConsumed={() => setQuickMessage(undefined)}
              />
            )}
            {activeTab === "charts"   && <ChartsView />}
            {activeTab === "insights" && <InsightsView />}
          </main>
        </div>
      </div>

      {/* Command palette — Ctrl+K / Cmd+K */}
      <CommandDialog open={cmdOpen} onOpenChange={setCmdOpen}>
        <CommandInput placeholder="Search actions and tabs…" />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>
          <CommandGroup heading="Navigation">
            <CommandItem onSelect={() => { handleTabChange("chat"); setCmdOpen(false); }}>
              Chat
            </CommandItem>
            <CommandItem onSelect={() => { handleTabChange("charts"); setCmdOpen(false); }}>
              Charts
            </CommandItem>
            <CommandItem onSelect={() => { handleTabChange("insights"); setCmdOpen(false); }}>
              Insights
            </CommandItem>
          </CommandGroup>
          <CommandGroup heading="Quick Actions">
            <CommandItem onSelect={() => handleQuickAction("auto-insights")}>
              Auto Insights
            </CommandItem>
            <CommandItem onSelect={() => handleQuickAction("trend-chart")}>
              Trend Chart
            </CommandItem>
            <CommandItem onSelect={() => handleQuickAction("data-summary")}>
              Data Summary
            </CommandItem>
            <CommandItem onSelect={() => handleQuickAction("clean-data")}>
              Clean Data
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </SessionProvider>
  );
};

export default Index;
