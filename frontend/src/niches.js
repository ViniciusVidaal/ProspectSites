export const NICHE_CATEGORIES = {
  "Saúde": [
    "Clínica odontológica", "Dentista", "Ortodontista", "Implantodontista",
    "Clínica médica", "Dermatologista", "Oftalmologista", "Fisioterapeuta",
    "Psicólogo", "Nutricionista", "Fonoaudiólogo", "Quiropraxista",
    "Clínica de estética", "Podólogo", "Laboratório de análises"
  ],
  "Beleza": [
    "Salão de beleza", "Barbearia", "Manicure", "Designer de sobrancelhas",
    "Extensão de cílios", "Maquiador", "Massoterapeuta", "Depilação",
    "Micropigmentação", "Clínica de harmonização facial", "Spa"
  ],
  "Casa e Serviços": [
    "Eletricista", "Encanador", "Marido de aluguel", "Chaveiro",
    "Dedetizadora", "Desentupidora", "Empresa de limpeza", "Jardinagem",
    "Piscineiro", "Ar-condicionado", "Assistência técnica", "Vidraceiro",
    "Serralheria", "Marcenaria", "Móveis planejados", "Reformas"
  ],
  "Construção": [
    "Arquiteto", "Engenheiro civil", "Construtora", "Imobiliária",
    "Corretor de imóveis", "Topografia", "Energia solar", "Gesso e drywall",
    "Pintor", "Loja de materiais de construção", "Marmoraria"
  ],
  "Automotivo": [
    "Oficina mecânica", "Auto elétrica", "Funilaria e pintura", "Lava-jato",
    "Estética automotiva", "Loja de pneus", "Autopeças", "Despachante",
    "Guincho", "Insulfilm", "Som automotivo", "Motocicletas"
  ],
  "Alimentação": [
    "Restaurante", "Pizzaria", "Hamburgueria", "Sushi", "Padaria",
    "Confeitaria", "Doceria", "Marmitaria", "Buffet", "Cafeteria",
    "Açaí", "Sorveteria", "Churrascaria", "Bar", "Distribuidora de bebidas"
  ],
  "Eventos": [
    "Fotógrafo", "Filmagem de eventos", "Cerimonialista", "Buffet para festas",
    "Decoração de festas", "Salão de festas", "DJ", "Banda para eventos",
    "Aluguel de brinquedos", "Aluguel de mesas e cadeiras", "Floricultura"
  ],
  "Educação": [
    "Escola infantil", "Reforço escolar", "Professor particular",
    "Escola de idiomas", "Curso profissionalizante", "Autoescola",
    "Escola de música", "Aulas de dança", "Artes marciais", "Personal trainer"
  ],
  "Profissionais": [
    "Advogado", "Contador", "Consultor empresarial", "Corretora de seguros",
    "Despachante documental", "Agência de marketing", "Designer gráfico",
    "Técnico de informática", "Segurança do trabalho", "Tradução"
  ],
  "Pets": [
    "Clínica veterinária", "Pet shop", "Banho e tosa", "Adestrador",
    "Hotel para cães", "Dog walker", "Creche para cães"
  ],
  "Comércio": [
    "Loja de roupas", "Loja de calçados", "Ótica", "Joalheria",
    "Papelaria", "Loja de presentes", "Celulares", "Informática",
    "Colchões", "Móveis", "Cortinas e persianas", "Produtos naturais"
  ],
  "Turismo e Transporte": [
    "Agência de viagens", "Pousada", "Hotel", "Aluguel de temporada",
    "Transportadora", "Frete e mudança", "Motoboy", "Transporte executivo",
    "Aluguel de carros", "Turismo local"
  ]
};

export const ALL_NICHES = Object.entries(NICHE_CATEGORIES).flatMap(
  ([category, niches]) => niches.map((name) => ({ name, category }))
);
