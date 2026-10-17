import Dashboard from "@/components/Dashboard";
import {notFound} from "next/navigation";
const pages=new Set(['','scanner','assets','asset','portfolio','models','research','autonomous-research','system','settings','watchlist','trade-ideas','orders','risk','providers','coverage','workers','forward-studies','model-portfolio','forward-evidence','decision-diagnostics','shadow-portfolio','alpha-library','advanced-research','market-structure','backtests','experiments','strategies','insiders','institutions','earnings','macro','themes','traders','options','crypto']);
export default async function Page({params}:{params:Promise<{slug?:string[]}>}) {
  const {slug=[]}=await params;
  if(!pages.has(slug[0]||'')||slug.length>2||(slug.length===2&&slug[0]!=='asset')) notFound();
  return <Dashboard/>;
}
