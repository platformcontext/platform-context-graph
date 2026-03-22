resource "aws_db_instance" "app" {
  identifier = "pcg-fixture-db"
  engine     = "postgres"
  username   = "postgres"
  password   = "postgres"
}
