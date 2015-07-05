# coding: utf-8
z = 'Mehl§agxraXRhLXJlemVwdGVyCwsSBVp1dGF0GAMM§500§|Zucker§agxraXRhLXJlemVwdGVyCwsSBVp1dGF0GAQM§§1 Hand voll|Milch§agxraXRhLXJlemVwdGVyCwsSBVp1dGF0GAUM§300§|'
z = z[:-1].split('|')
for n, k, m, mq in [tuple(zz.split('§')) for zz in z]:
  print n
  print k
  print m
  print mq, '\n'