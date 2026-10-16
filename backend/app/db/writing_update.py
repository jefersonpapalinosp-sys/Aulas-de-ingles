"""Compatibilidade fechada para o antigo atalho destrutivo de rubricas."""

from sqlalchemy.ext.asyncio import AsyncSession


async def update_writing_rubrics(session: AsyncSession) -> int:
    """Recusa o fluxo legado antes de consultar ou alterar o banco.

    Mantido temporariamente para que integrações antigas falhem de forma
    explícita. A auditoria atual encontrou mudanças que afetam a avaliação;
    preservar IDs não torna uma sobrescrita semanticamente segura.
    """
    del session
    raise ValueError(
        "Atualização direta de rubricas desativada; use a auditoria editorial "
        "e publique uma nova versão homologada."
    )
