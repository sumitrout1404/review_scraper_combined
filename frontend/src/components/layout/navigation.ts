import { Activity, LayoutDashboard, MessagesSquare, Tags, type LucideIcon } from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', label: 'Overview', description: 'Scores, trends and what needs attention', icon: LayoutDashboard },
  { to: '/reviews', label: 'Reviews', description: 'Read individual guest reviews', icon: MessagesSquare },
  { to: '/topics', label: 'Topics', description: 'What guests praise and complain about', icon: Tags },
  { to: '/data-health', label: 'Data health', description: 'How and when data is collected', icon: Activity },
];
