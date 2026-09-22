import Link from "next/link";

export default function Home() {
  return (
    <main className="landing">
      <section className="landing-hero" aria-labelledby="landing-title">
        <p className="eyebrow">Platformă operațională</p>
        <h1 id="landing-title">GovControl</h1>
        <p>Un spațiu de lucru clar pentru termene, obligații și risc juridic în administrația publică.</p>
        <Link href="/legal">Deschide panoul de control</Link>
        <small>Începi cu obligațiile care necesită atenție.</small>
      </section>

      <section className="landing-benefits" aria-label="Ce poți face în GovControl">
        <article><span>01</span><h2>Vezi prioritățile</h2><p>Identifică imediat termenele depășite sau apropiate.</p></article>
        <article><span>02</span><h2>Actualizezi progresul</h2><p>Schimbă statusul și păstrează documentele justificative lângă obligație.</p></article>
        <article><span>03</span><h2>Păstrezi trasabilitatea</h2><p>Dosarele, hotărârile, executările și notificările rămân în același flux.</p></article>
      </section>
    </main>
  );
}
