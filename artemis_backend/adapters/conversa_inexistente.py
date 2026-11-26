from fastapi import HTTPException, status


def nao_encontrada() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada")
