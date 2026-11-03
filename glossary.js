/* Glossary tooltips — wraps known terms with a styled span; hover/click shows
   a Bangla explanation. Include with <script src="glossary.js"></script> +
   <link rel="stylesheet" href="glossary.css">. Works on file:// too. */
(function () {
  const TERMS = {
    'MRR': 'Monthly Recurring Revenue — প্রতি মাসে সাবস্ক্রিপশন থেকে আসা মোট টাকা। ১০০ দোকান × ১,২০০ টাকা = ১.২ লাখ MRR',
    'ARR': 'Annual Recurring Revenue — MRR × ১২। ইনভেস্টররা কোম্পানির দাম এটার মাল্টিপল দিয়ে মাপে',
    'ARPU': 'Average Revenue Per User — প্রতি দোকান থেকে মাসে গড়ে কত টাকা আসে',
    'TAM': 'Total Addressable Market — পুরো সম্ভাব্য মার্কেট (আমাদের ক্ষেত্রে ~৩৯.৫ লাখ দোকান)',
    'SAM': 'Serviceable Addressable Market — আমরা বাস্তবে যাদের সার্ভ করতে পারি (১-২ লাখ ডিজিটালি-রেডি দোকান)',
    'SOM': 'Serviceable Obtainable Market — নির্দিষ্ট সময়ে যা পাওয়া সম্ভব (৩ বছরে ১-২% = ১-২ হাজার দোকান)',
    'CAC': 'Customer Acquisition Cost — একটা পেইং দোকান আনতে মোট কত খরচ (সেলস+মার্কেটিং)',
    'LTV': 'Lifetime Value — একটা দোকান থেকে পুরো সম্পর্কজুড়ে মোট কত আয় হয়',
    'Churn': 'চার্ন — মাসে কত % কাস্টমার চলে যায়। কম হওয়া মানে দোকানদার পছন্দ করছে',
    'MAU': 'Monthly Active Users — মাসে অন্তত একবার অ্যাপ ব্যবহার করে এমন মোট ইউজার',
    'DAU': 'Daily Active Users — প্রতিদিন ব্যবহার করে এমন ইউজার',
    'ESOP': 'Employee Stock Ownership Plan — কর্মচারীদের জন্য রাখা শেয়ার পুল (সাধারণত ৫-১০%)',
    'Vesting': 'ভেস্টিং — শেয়ার ধীরে ধীরে অর্জন হয় নির্দিষ্ট সময়ে (সাধারণত ৪ বছর), আগে চলে গেলে হারান',
    'Cliff': 'ক্লিফ — ভেস্টিংয়ের প্রথম বাধা (সাধারণত ১ বছর); এর আগে কেউ চলে গেলে ০% শেয়ার পায়',
    'Pre-money': 'টাকা ঢোকার আগে কোম্পানির দাম। $50K @ $450K pre = ইনভেস্টর পায় ১০%',
    'Post-money': 'Pre-money + ইনভেস্টমেন্ট = টাকা ঢোকার পরের দাম',
    'Cap table': 'ক্যাপিটালাইজেশন টেবিল — কার হাতে কত % শেয়ার তার তালিকা',
    'Dilution': 'ডাইলুশন — নতুন শেয়ার ইস্যু হলে আগের মালিকদের % কমে যাওয়া',
    'Runway': 'রানওয়ে — হাতের টাকায় আর কত মাস চলা যাবে',
    'Term sheet': 'ইনভেস্টমেন্টের শর্তের সারসংক্ষেপ — মূল কাগজের আগের ড্রাফট',
    'Due diligence': 'ইনভেস্টরের যাচাই-বাছাই — কোম্পানির কাগজ, ট্র্যাকশন, কোড সব চেক করা',
    'Equity': 'ইক্যুইটি — কোম্পানির মালিকানা (শেয়ার)',
    'Liquidation preference': 'কোম্পানি বিক্রি/বন্ধ হলে আগে ইনভেস্টর তার টাকা ফেরত পায় — ১x স্ট্যান্ডার্ড',
    'Anti-dilution': 'পরের রাউন্ড কম দামে হলে পুরনো ইনভেস্টরের শেয়ার বাড়ে — "full ratchet" লাল পতাকা',
    'Drag-along': 'ম্যাজোরিটি কোম্পানি বিক্রি করলে মাইনোরিটিকেও যেতে হয়',
    'Tag-along': 'ম্যাজোরিটি শেয়ার বিক্রি করলে মাইনোরিটিও সমানুপাতে বিক্রি করতে পারে',
    'Pro-rata': 'পরের রাউন্ডে আগের % ধরে রাখতে আবার ইনভেস্ট করার অধিকার',
    'SAFE': 'Simple Agreement for Future Equity — এখন টাকা, পরের রাউন্ডে শেয়ারে কনভার্ট (discount+cap সহ)',
    'SAFI': 'SAFE-এর বাংলাদেশি সংস্করণ — একই লজিক, দেশি আইনে লেখা',
    'Freemium': 'ফ্রি টিয়ার দিয়ে ঢুকিয়ে পরে পেইডে আপগ্রেড করানোর মডেল — টালিখাতার প্লেবুক',
    'SaaS': 'Software as a Service — মাসিক ভাড়ায় সফটওয়্যার ব্যবহারের মডেল',
    'B2B': 'Business to Business — ব্যবসায়িক গ্রাহকের কাছে বিক্রি (আমরা দোকানদারের কাছে)',
    'POS': 'Point of Sale — দোকানের কাউন্টারে বিক্রি করার সিস্টেম (বিলিং মেশিন/অ্যাপ)',
    'IMEI': 'মোবাইল ফোনের ইউনিক ১৫-সংখ্যার পরিচয় — প্রতিটা হ্যান্ডসেট ট্র্যাক করতে লাগে',
    'EMI': 'Equated Monthly Installment — কিস্তিতে বিক্রি, মাসিক কিস্তি',
    'NEIR': 'National Equipment Identity Register — BTRC-র হ্যান্ডসেট রেজিস্ট্রেশন সিস্টেম',
    'PSP': 'Payment Service Provider — বাংলাদেশ ব্যাংকের পেমেন্ট লাইসেন্স (টালিখাতার TallyPay যেমন)',
    'MFS': 'Mobile Financial Service — bKash/Nagad-এর মতো মোবাইল মানি সার্ভিস',
    'API': 'Application Programming Interface — দুই সিস্টেম একে অপরের সাথে কথা বলার নিয়ম',
    'RJSC': 'Registrar of Joint Stock Companies — কোম্পানি রেজিস্ট্রেশনের সরকারি অফিস',
    'BIDA': 'Bangladesh Investment Development Authority — বিদেশি ইনভেস্টমেন্টের অনুমতি দেয়',
    'NBR': 'National Board of Revenue — জাতীয় রাজস্ব বোর্ড (ট্যাক্স/VAT)',
    'TIN': 'Tax Identification Number — করদাতার পরিচয় নম্বর',
    'BIN': 'Business Identification Number — VAT রেজিস্ট্রেশন নম্বর',
    'VAT': 'Value Added Tax — মূল্য সংযোজন কর, বিক্রির উপর সরকারি কর',
    'GTM': 'Go-To-Market — প্রোডাক্ট কীভাবে কাস্টমারের কাছে পৌঁছাবে তার প্ল্যান',
    'Unit economics': 'একজন কাস্টমারে লাভ-লোকসানের হিসাব — LTV vs CAC',
    'MoM': 'Month over Month — এক মাসের তুলনায় আগের মাসের গ্রোথ',
  };

  const names = Object.keys(TERMS).sort((a, b) => b.length - a.length);
  const rx = new RegExp('\\b(' + names.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')\\b', 'g');

  const SKIP = new Set(['SCRIPT', 'STYLE', 'CODE', 'PRE', 'A', 'ABBR', 'TEXTAREA']);
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
      let p = node.parentElement;
      while (p) {
        if (SKIP.has(p.tagName) || p.classList.contains('gterm')) return NodeFilter.FILTER_REJECT;
        p = p.parentElement;
      }
      return rx.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });

  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);

  for (const node of nodes) {
    rx.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0, m;
    while ((m = rx.exec(node.nodeValue))) {
      if (m.index > last) frag.appendChild(document.createTextNode(node.nodeValue.slice(last, m.index)));
      const span = document.createElement('span');
      span.className = 'gterm';
      span.textContent = m[0];
      span.dataset.tip = TERMS[m[0]];
      frag.appendChild(span);
      last = m.index + m[0].length;
    }
    frag.appendChild(document.createTextNode(node.nodeValue.slice(last)));
    node.parentNode.replaceChild(frag, node);
  }

  // Tap/click support for touch devices
  document.addEventListener('click', e => {
    document.querySelectorAll('.gterm.open').forEach(s => {
      if (s !== e.target) s.classList.remove('open');
    });
    if (e.target.classList && e.target.classList.contains('gterm')) {
      e.target.classList.toggle('open');
    }
  });
})();
